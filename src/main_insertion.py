import osmnx as ox
import pandas as pd
from shapely.geometry import Point
from neo4j import GraphDatabase
import time
import geocoder
import logging
from typing import Tuple, Optional, List, Dict
import requests
from dataclasses import dataclass
import math

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class PharmacyInfo:
    name: str
    latitude: float
    longitude: float
    distance_km: float
    hops: int
    nearest_node: int

class GeoSpatialPharmacyFinder:
    def __init__(self, place: str, neo4j_uri: str, neo4j_user: str, neo4j_password: str, database: str = "pharmaciegraph"):
        self.place = place
        self.neo4j_uri = neo4j_uri
        self.neo4j_user = neo4j_user
        self.neo4j_password = neo4j_password
        self.database = database
        self.driver = None
        self.graph = None
        
    def get_user_location(self) -> Tuple[float, float]:
        """Obtenir la localisation de l'utilisateur avec plusieurs méthodes de fallback"""
        try:
            # Méthode 1: Géolocalisation IP
            g = geocoder.ip('me')
            if g.lat and g.lng:
                logger.info(f"Position trouvée via IP: {g.lat}, {g.lng}")
                return g.lat, g.lng
        except Exception as e:
            logger.warning(f"Échec géolocalisation IP: {e}")
        
        try:
            # Méthode 2: Géolocalisation basée sur l'adresse IP avec service alternatif
            response = requests.get('http://ipapi.co/json/', timeout=5)
            if response.status_code == 200:
                data = response.json()
                if 'latitude' in data and 'longitude' in data:
                    logger.info(f"Position trouvée via ipapi: {data['latitude']}, {data['longitude']}")
                    return data['latitude'], data['longitude']
        except Exception as e:
            logger.warning(f"Échec géolocalisation ipapi: {e}")
        
        # Fallback: Position par défaut (Fès, Maroc)
        default_lat, default_lon = 34.044422, -4.988163
        logger.info(f"Utilisation position par défaut: {default_lat}, {default_lon}")
        return default_lat, default_lon

    def connect_to_neo4j(self) -> bool:
        """Établir la connexion à Neo4j avec gestion d'erreurs"""
        try:
            self.driver = GraphDatabase.driver(
                self.neo4j_uri, 
                auth=(self.neo4j_user, self.neo4j_password),
                max_connection_lifetime=3600,
                keep_alive=True
            )
            # Test de connexion
            with self.driver.session(database=self.database) as session:
                session.run("RETURN 1")
            logger.info("Connexion Neo4j établie avec succès")
            return True
        except Exception as e:
            logger.error(f"Erreur connexion Neo4j: {e}")
            return False

    def extract_osm_data(self) -> Tuple[any, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Extraire les données d'OpenStreetMap"""
        try:
            logger.info(f"Téléchargement des données OSM pour {self.place}...")
            
            # Configuration OSM pour de meilleures performances
            ox.settings.use_cache = True
            ox.settings.cache_folder = "./osm_cache"
            
            # Télécharger le graphe routier
            G = ox.graph_from_place(self.place, network_type="walk", simplify=True)
            nodes, edges = ox.graph_to_gdfs(G)
            
            logger.info(f"Graphe téléchargé: {len(nodes)} nœuds, {len(edges)} arêtes")
            
            # Extraire les pharmacies avec plus d'informations
            logger.info("Extraction des pharmacies...")
            pharmacies = ox.features_from_place(
                self.place, 
                tags={"amenity": "pharmacy"}
            )
            
            if pharmacies.empty:
                logger.warning("Aucune pharmacie trouvée, essai avec des tags alternatifs...")
                # Essayer avec des tags alternatifs
                pharmacies = ox.features_from_place(
                    self.place,
                    tags={"shop": "pharmacy"}
                )
            
            # Filtrer pour ne garder que les points
            pharmacies = pharmacies[pharmacies.geometry.type == "Point"]
            
            # Nettoyer et préparer les données des pharmacies
            pharmacy_columns = ["name", "geometry"]
            available_columns = [col for col in pharmacy_columns if col in pharmacies.columns]
            pharmacies = pharmacies[available_columns].reset_index(drop=True)
            
            # Gérer les noms manquants
            if "name" not in pharmacies.columns:
                pharmacies["name"] = "Pharmacie sans nom"
            else:
                pharmacies["name"] = pharmacies["name"].fillna("Pharmacie sans nom")
            
            # Trouver le nœud routier le plus proche pour chaque pharmacie
            logger.info("Calcul des nœuds les plus proches...")
            pharmacies["nearest_node"] = pharmacies["geometry"].apply(
                lambda p: ox.distance.nearest_nodes(G, p.x, p.y)
            )
            
            logger.info(f"{len(pharmacies)} pharmacies trouvées")
            self.graph = G
            return G, nodes, edges, pharmacies
            
        except Exception as e:
            logger.error(f"Erreur extraction données OSM: {e}")
            raise

    def setup_database(self):
        """Configurer la base de données Neo4j avec les index appropriés"""
        with self.driver.session(database=self.database) as session:
            try:
                # Créer les contraintes et index pour de meilleures performances
                session.run("CREATE CONSTRAINT intersection_id IF NOT EXISTS FOR (n:Intersection) REQUIRE n.id IS UNIQUE")
                session.run("CREATE CONSTRAINT pharmacy_name IF NOT EXISTS FOR (p:Pharmacy) REQUIRE (p.name, p.latitude, p.longitude) IS UNIQUE")
                session.run("CREATE INDEX intersection_location IF NOT EXISTS FOR (n:Intersection) ON (n.latitude, n.longitude)")
                session.run("CREATE INDEX pharmacy_location IF NOT EXISTS FOR (p:Pharmacy) ON (p.latitude, p.longitude)")
                logger.info("Index et contraintes créés")
            except Exception as e:
                logger.warning(f"Erreur création index: {e}")

    def clear_database(self):
        """Nettoyer la base de données avant insertion"""
        with self.driver.session(database=self.database) as session:
            try:
                session.run("MATCH (n) DETACH DELETE n")
                logger.info("Base de données nettoyée")
            except Exception as e:
                logger.error(f"Erreur nettoyage base: {e}")

    def insert_data(self, nodes: pd.DataFrame, edges: pd.DataFrame, pharmacies: pd.DataFrame):
        """Insérer les données dans Neo4j avec traitement par lots"""
        with self.driver.session(database=self.database) as session:
            try:
                # Insertion des nœuds par lots
                logger.info("Insertion des nœuds routiers...")
                batch_size = 1000
                node_batches = [nodes[i:i+batch_size] for i in range(0, len(nodes), batch_size)]
                
                for batch in node_batches:
                    node_data = [
                        {"id": int(node_id), "lat": float(row["y"]), "lon": float(row["x"])}
                        for node_id, row in batch.iterrows()
                    ]
                    session.run("""
                        UNWIND $nodes AS node
                        MERGE (n:Intersection {id: node.id})
                        SET n.latitude = node.lat, n.longitude = node.lon
                    """, nodes=node_data)
                
                # Insertion des arêtes par lots
                logger.info("Insertion des relations routières...")
                edge_batches = [edges[i:i+batch_size] for i in range(0, len(edges), batch_size)]
                
                for batch in edge_batches:
                    edge_data = []
                    for index, row in batch.iterrows():
                        u, v = index[0], index[1]
                        dist = float(row.get("length", 0))
                        edge_data.append({"u": int(u), "v": int(v), "distance": dist})
                    
                    session.run("""
                        UNWIND $edges AS edge
                        MATCH (a:Intersection {id: edge.u}), (b:Intersection {id: edge.v})
                        MERGE (a)-[:CONNECTED {distance: edge.distance}]->(b)
                    """, edges=edge_data)
                
                # Insertion des pharmacies
                logger.info("Insertion des pharmacies...")
                pharmacy_data = []
                for i, row in pharmacies.iterrows():
                    geom = row["geometry"]
                    pharmacy_data.append({
                        "name": str(row["name"]),
                        "lat": float(geom.y),
                        "lon": float(geom.x),
                        "node_id": int(row["nearest_node"])
                    })
                
                session.run("""
                    UNWIND $pharmacies AS pharmacy
                    MERGE (p:Pharmacy {name: pharmacy.name, latitude: pharmacy.lat, longitude: pharmacy.lon})
                    WITH p, pharmacy
                    MATCH (n:Intersection {id: pharmacy.node_id})
                    MERGE (p)-[:NEAR]->(n)
                """, pharmacies=pharmacy_data)
                
                logger.info("Insertion des données terminée")
                
            except Exception as e:
                logger.error(f"Erreur insertion données: {e}")
                raise

    def calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculer la distance haversine entre deux points"""
        R = 6371  # Rayon de la Terre en km
        
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        a = (math.sin(delta_lat/2)**2 + 
             math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        
        return R * c

    def find_closest_pharmacies(self, user_lat: float, user_lon: float, limit: int = 5) -> List[PharmacyInfo]:
        """Trouver les pharmacies les plus proches"""
        try:
            user_node = ox.distance.nearest_nodes(self.graph, X=user_lon, Y=user_lat)
            logger.info(f"Nœud utilisateur le plus proche: {user_node}")
            
            with self.driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (start:Intersection {id: $uid})
                    MATCH (p:Pharmacy)-[:NEAR]->(target:Intersection)
                    CALL apoc.algo.dijkstra(start, target, 'CONNECTED', 'distance') YIELD path, weight
                    RETURN p.name AS pharmacy_name, 
                           p.latitude AS pharmacy_lat, 
                           p.longitude AS pharmacy_lon,
                           weight AS total_distance,
                           length(path) AS hops,
                           target.id AS nearest_node
                    ORDER BY total_distance ASC
                    LIMIT $limit
                """, uid=user_node, limit=limit)
                
                pharmacies = []
                for record in result:
                    # Calculer la distance réelle
                    distance_km = self.calculate_distance(
                        user_lat, user_lon,
                        record["pharmacy_lat"], record["pharmacy_lon"]
                    )
                    
                    pharmacy = PharmacyInfo(
                        name=record["pharmacy_name"],
                        latitude=record["pharmacy_lat"],
                        longitude=record["pharmacy_lon"],
                        distance_km=distance_km,
                        hops=record["hops"],
                        nearest_node=record["nearest_node"]
                    )
                    pharmacies.append(pharmacy)
                
                return pharmacies
                
        except Exception as e:
            logger.error(f"Erreur recherche pharmacies: {e}")
            # Fallback: recherche simple sans Dijkstra
            return self._find_closest_pharmacies_simple(user_lat, user_lon, limit)

    def _find_closest_pharmacies_simple(self, user_lat: float, user_lon: float, limit: int = 5) -> List[PharmacyInfo]:
        """Méthode de fallback pour trouver les pharmacies les plus proches"""
        try:
            user_node = ox.distance.nearest_nodes(self.graph, X=user_lon, Y=user_lat)
            
            with self.driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (start:Intersection {id: $uid})
                    MATCH (p:Pharmacy)-[:NEAR]->(target:Intersection)
                    MATCH path = shortestPath((start)-[:CONNECTED*..50]-(target))
                    RETURN p.name AS pharmacy_name, 
                           p.latitude AS pharmacy_lat, 
                           p.longitude AS pharmacy_lon,
                           length(path) AS hops,
                           target.id AS nearest_node
                    ORDER BY hops ASC
                    LIMIT $limit
                """, uid=user_node, limit=limit)
                
                pharmacies = []
                for record in result:
                    distance_km = self.calculate_distance(
                        user_lat, user_lon,
                        record["pharmacy_lat"], record["pharmacy_lon"]
                    )
                    
                    pharmacy = PharmacyInfo(
                        name=record["pharmacy_name"],
                        latitude=record["pharmacy_lat"],
                        longitude=record["pharmacy_lon"],
                        distance_km=distance_km,
                        hops=record["hops"],
                        nearest_node=record["nearest_node"]
                    )
                    pharmacies.append(pharmacy)
                
                return pharmacies
                
        except Exception as e:
            logger.error(f"Erreur recherche simple: {e}")
            return []

    def get_route_to_pharmacy(self, user_lat: float, user_lon: float, pharmacy_lat: float, pharmacy_lon: float):
        """Obtenir l'itinéraire détaillé vers une pharmacie"""
        try:
            user_node = ox.distance.nearest_nodes(self.graph, X=user_lon, Y=user_lat)
            pharmacy_node = ox.distance.nearest_nodes(self.graph, X=pharmacy_lon, Y=pharmacy_lat)
            
            route = ox.shortest_path(self.graph, user_node, pharmacy_node, weight='length')
            if route:
                route_coords = [(self.graph.nodes[node]['y'], self.graph.nodes[node]['x']) for node in route]
                return route_coords
            return []
            
        except Exception as e:
            logger.error(f"Erreur calcul itinéraire: {e}")
            return []

    def close_connection(self):
        """Fermer la connexion Neo4j"""
        if self.driver:
            self.driver.close()
            logger.info("Connexion Neo4j fermée")

def main():
    # Configuration
    PLACE = "Fès, Maroc"
    NEO4J_URI = "bolt://localhost:7687"
    NEO4J_USER = "neo4j"
    NEO4J_PASSWORD = "test1234"
    
    # Créer l'application
    app = GeoSpatialPharmacyFinder(PLACE, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    
    try:
        # Obtenir la position utilisateur
        user_lat, user_lon = app.get_user_location()
        logger.info(f"Position utilisateur: {user_lat}, {user_lon}")
        
        # Se connecter à Neo4j
        if not app.connect_to_neo4j():
            logger.error("Impossible de se connecter à Neo4j")
            return
        
        # Configurer la base de données
        app.setup_database()
        
        # Demander si on doit recharger les données
        reload_data = input("Voulez-vous recharger les données OSM ? (o/N): ").lower().startswith('o')
        
        if reload_data:
            # Extraire les données OSM
            G, nodes, edges, pharmacies = app.extract_osm_data()
            
            # Nettoyer et insérer les données
            app.clear_database()
            app.insert_data(nodes, edges, pharmacies)
        
        # Rechercher les pharmacies les plus proches
        logger.info("Recherche des pharmacies les plus proches...")
        closest_pharmacies = app.find_closest_pharmacies(user_lat, user_lon, limit=5)
        
        if closest_pharmacies:
            print("\n🏥 PHARMACIES LES PLUS PROCHES:")
            print("=" * 50)
            for i, pharmacy in enumerate(closest_pharmacies, 1):
                print(f"{i}. {pharmacy.name}")
                print(f"   📍 Distance: {pharmacy.distance_km:.2f} km")
                print(f"   🗺️  Coordonnées: {pharmacy.latitude:.6f}, {pharmacy.longitude:.6f}")
                print(f"   🛣️  Étapes de route: {pharmacy.hops}")
                print()
                
            # Optionnel: obtenir l'itinéraire vers la première pharmacie
            if len(closest_pharmacies) > 0:
                first_pharmacy = closest_pharmacies[0]
                route = app.get_route_to_pharmacy(
                    user_lat, user_lon,
                    first_pharmacy.latitude, first_pharmacy.longitude
                )
                if route:
                    print(f"📍 Itinéraire vers {first_pharmacy.name} ({len(route)} points)")
        else:
            print("❌ Aucune pharmacie trouvée dans la zone.")
            
    except Exception as e:
        logger.error(f"Erreur dans l'application principale: {e}")
    finally:
        app.close_connection()

if __name__ == "__main__":
    main()