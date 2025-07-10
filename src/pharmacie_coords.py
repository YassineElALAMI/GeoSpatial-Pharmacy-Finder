import osmnx as ox
import networkx as nx
from neo4j import GraphDatabase
import requests
import math
import logging
from typing import Tuple, List, Optional
from dataclasses import dataclass
import folium
from folium import plugins
import webbrowser
import os

# Logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class UserLocation:
    latitude: float
    longitude: float
    address: str
    method: str

@dataclass
class PharmacyResult:
    name: str
    latitude: float
    longitude: float
    distance_km: float
    walking_time_minutes: int
    hops: int
    address: Optional[str] = None

class PharmacyFinder:
    def __init__(self, neo4j_uri: str, neo4j_user: str, neo4j_password: str, database: str = "pharmaciegraph"):
        self.neo4j_uri = neo4j_uri
        self.neo4j_user = neo4j_user
        self.neo4j_password = neo4j_password
        self.database = database
        self.driver = None
        self.user_location = None
        self.graph = None  # Store OSMnx graph for reuse

    def connect_to_neo4j(self) -> bool:
        try:
            self.driver = GraphDatabase.driver(
                self.neo4j_uri,
                auth=(self.neo4j_user, self.neo4j_password),
                max_connection_lifetime=3600
            )
            with self.driver.session(database=self.database) as session:
                result = session.run("RETURN 1 as test")
                result.single()
            logger.info("✅ Connected to Neo4j")
            return True
        except Exception as e:
            logger.error(f"❌ Neo4j connection error: {e}")
            return False

    def get_detailed_location(self) -> UserLocation:
        try:
            from get_location import get_location_from_browser
            data = get_location_from_browser()
            if data:
                lat = data["latitude"]
                lon = data["longitude"]
                address = self.get_address_from_coords(lat, lon)
                return UserLocation(lat, lon, address, "Browser (HTML5 Geolocation)")
        except Exception as e:
            logger.warning(f"🔁 Failed to get location from browser: {e}")

        logger.info("Using fallback fixed location")
        return UserLocation(
            latitude=34.0349,
            longitude=-4.9764,
            address="Fès, Morocco (fixed position)",
            method="Fixed position"
        )

    def calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        R = 6371
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat/2)**2 +
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

    def estimate_walking_time(self, distance_km: float) -> int:
        return int((distance_km / 5.0) * 60)

    def get_address_from_coords(self, lat: float, lon: float) -> str:
        try:
            response = requests.get(
                f"https://nominatim.openstreetmap.org/reverse",
                params={
                    'lat': lat,
                    'lon': lon,
                    'format': 'json',
                    'addressdetails': 1
                },
                headers={'User-Agent': 'PharmacyFinder/1.0'},
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                return data.get('display_name', 'Address not available')
        except Exception:
            pass
        return f"Latitude: {lat:.6f}, Longitude: {lon:.6f}"

    def find_nearest_pharmacies(self, limit: int = 4) -> List[PharmacyResult]:
        if not self.user_location:
            self.user_location = self.get_detailed_location()

        try:
            self.graph = ox.graph_from_point(
                (self.user_location.latitude, self.user_location.longitude),
                dist=5000,
                network_type="walk"
            )
            user_node = ox.distance.nearest_nodes(
                self.graph,
                X=self.user_location.longitude,
                Y=self.user_location.latitude
            )
            logger.info(f"🎯 User node: {user_node}")
        except Exception as e:
            logger.warning(f"Unable to load OSM graph: {e}")
            user_node = None

        with self.driver.session(database=self.database) as session:
            try:
                if user_node:
                    result = session.run("""
                        MATCH (start:Intersection {id: $uid})
                        MATCH (p:Pharmacy)-[:NEAR]->(target:Intersection)
                        MATCH path = shortestPath((start)-[:CONNECTED*..100]-(target))
                        WITH p, path, 
                             reduce(totalDist = 0, r in relationships(path) | totalDist + r.distance) as totalDistance
                        RETURN p.name AS pharmacy_name, 
                               p.latitude AS pharmacy_lat, 
                               p.longitude AS pharmacy_lon,
                               totalDistance,
                               length(path) AS hops
                        ORDER BY totalDistance ASC
                        LIMIT $limit
                    """, uid=user_node, limit=limit)
                else:
                    result = session.run("""
                        MATCH (p:Pharmacy)
                        WITH p, 
                             sqrt(pow(p.latitude - $user_lat, 2) + pow(p.longitude - $user_lon, 2)) as euclideanDist
                        RETURN p.name AS pharmacy_name, 
                               p.latitude AS pharmacy_lat, 
                               p.longitude AS pharmacy_lon,
                               euclideanDist * 111.32 as totalDistance,
                               0 as hops
                        ORDER BY euclideanDist ASC
                        LIMIT $limit
                    """, user_lat=self.user_location.latitude, user_lon=self.user_location.longitude, limit=limit)

                pharmacies = []
                for record in result:
                    distance_km = self.calculate_distance(
                        self.user_location.latitude, self.user_location.longitude,
                        record["pharmacy_lat"], record["pharmacy_lon"]
                    )
                    walking_time = self.estimate_walking_time(distance_km)
                    address = self.get_address_from_coords(
                        record["pharmacy_lat"], record["pharmacy_lon"]
                    )
                    pharmacies.append(PharmacyResult(
                        name=record["pharmacy_name"],
                        latitude=record["pharmacy_lat"],
                        longitude=record["pharmacy_lon"],
                        distance_km=distance_km,
                        walking_time_minutes=walking_time,
                        hops=record["hops"],
                        address=address
                    ))
                return pharmacies
            except Exception as e:
                logger.error(f"❌ Neo4j query error: {e}")
                return []

    def get_route_path(self, start_lat: float, start_lon: float, end_lat: float, end_lon: float) -> Optional[List[Tuple[float, float]]]:
        """Find and return shortest walking route as list of lat-lon points"""
        if not self.graph:
            return None
        try:
            orig_node = ox.distance.nearest_nodes(self.graph, start_lon, start_lat)
            dest_node = ox.distance.nearest_nodes(self.graph, end_lon, end_lat)
            route = nx.shortest_path(self.graph, orig_node, dest_node, weight='length')
            route_coords = [(self.graph.nodes[n]['y'], self.graph.nodes[n]['x']) for n in route]
            return route_coords
        except Exception as e:
            logger.warning(f"⚠️ Route calculation failed: {e}")
            return None

    def create_interactive_map(self, pharmacies: List[PharmacyResult]) -> Optional[str]:
        if not self.user_location or not pharmacies:
            return None

        m = folium.Map(
            location=[self.user_location.latitude, self.user_location.longitude],
            zoom_start=14,
            tiles='OpenStreetMap'
        )

        folium.Marker(
            [self.user_location.latitude, self.user_location.longitude],
            popup=f"<b>Your Position</b><br>{self.user_location.address}",
            tooltip="You are here",
            icon=folium.Icon(color='red', icon='user', prefix='fa')
        ).add_to(m)

        colors = ['green', 'blue', 'orange', 'purple']
        for i, pharmacy in enumerate(pharmacies):
            color = colors[i] if i < len(colors) else 'gray'
            popup_text = f"""
            <b>{pharmacy.name}</b><br>
            📍 Distance: {pharmacy.distance_km:.2f} km<br>
            🚶 Walking time: {pharmacy.walking_time_minutes} min<br>
            📍 {pharmacy.address[:100]}...
            """
            folium.Marker(
                [pharmacy.latitude, pharmacy.longitude],
                popup=popup_text,
                tooltip=f"{i + 1}. {pharmacy.name}",
                icon=folium.Icon(color=color, icon='plus', prefix='fa')
            ).add_to(m)

            if i == 0:
                route = self.get_route_path(
                    self.user_location.latitude,
                    self.user_location.longitude,
                    pharmacy.latitude,
                    pharmacy.longitude
                )
                if route:
                    folium.PolyLine(
                        locations=route,
                        color='red',
                        weight=4,
                        opacity=0.8
                    ).add_to(m)

        map_file = 'pharmacy_map.html'
        m.save(map_file)
        return map_file

    def display_results(self, pharmacies: List[PharmacyResult]):
        print("\n" + "="*80)
        print("🎯 YOUR CURRENT LOCATION")
        print("="*80)
        print(f"📍 Latitude: {self.user_location.latitude:.6f}")
        print(f"📍 Longitude: {self.user_location.longitude:.6f}")
        print(f"🏠 Address: {self.user_location.address}")
        print(f"🔍 Method: {self.user_location.method}")
        
        if pharmacies:
            print("\n" + "="*80)
            print("💊 TOP 4 NEAREST PHARMACIES")
            print("="*80)
            for i, pharmacy in enumerate(pharmacies, 1):
                print(f"\n🏥 {i}. {pharmacy.name}")
                print(f"   📍 Distance: {pharmacy.distance_km:.2f} km")
                print(f"   🚶 Estimated walking time: {pharmacy.walking_time_minutes} minutes")
                print(f"   🗺️  Coordinates: {pharmacy.latitude:.6f}, {pharmacy.longitude:.6f}")
                if pharmacy.hops > 0:
                    print(f"   🛣️  Route steps: {pharmacy.hops}")
                print(f"   📍 Address: {pharmacy.address}")
                if i == 1:
                    print("   ⭐ CLOSEST PHARMACY ⭐")
                print("-" * 70)

            map_file = self.create_interactive_map(pharmacies)
            if map_file:
                print(f"\n🗺️  Interactive map created: {map_file}")
                try:
                    webbrowser.open(f"file://{os.path.abspath(map_file)}")
                    print("🌐 Opening the map in your browser...")
                except Exception as e:
                    print(f"❌ Could not open the map automatically: {e}")
                    print(f"You can open it manually: {os.path.abspath(map_file)}")
        else:
            print("\n❌ No pharmacy found in the database.")
            print("Make sure data has been properly loaded into Neo4j.")

    def close_connection(self):
        if self.driver:
            self.driver.close()
            logger.info("🔌 Neo4j connection closed")

def main():
    NEO4J_URI = "bolt://localhost:7687"
    NEO4J_USER = "neo4j"
    NEO4J_PASSWORD = "test1234"

    finder = PharmacyFinder(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    try:
        print("🔍 Searching for the nearest pharmacies...")
        print("⏳ Connecting to Neo4j...")
        if not finder.connect_to_neo4j():
            print("❌ Unable to connect to Neo4j. Check your configuration.")
            return

        print("📍 Detecting your location...")
        finder.user_location = finder.get_detailed_location()

        print("🔎 Querying pharmacies from the database...")
        pharmacies = finder.find_nearest_pharmacies(limit=4)

        finder.display_results(pharmacies)
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
    except Exception as e:
        logger.error(f"❌ Application error: {e}")
        print(f"❌ An error occurred: {e}")
    finally:
        finder.close_connection()

if __name__ == "__main__":
    main()
