# GeoSpatial Pharmacy Finder

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Neo4j](https://img.shields.io/badge/neo4j-v5.x-blue.svg)](https://neo4j.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

The GeoSpatial Pharmacy Finder is an advanced Python application designed to help users locate the nearest pharmacies in their area using a combination of Neo4j graph database technology and OpenStreetMap (OSM) data. This project was developed as part of a Big Data Analytics course project and showcases the power of graph databases in solving real-world geospatial problems.

## 🌟 Overview

The application leverages multiple technologies to provide an efficient and accurate pharmacy location system:

- **Graph Database:** Neo4j v5.x for storing and querying spatial relationships
- **Geospatial Data:** OpenStreetMap data via OSMnx for road networks and points of interest
- **Search Algorithms:** Multiple pathfinding algorithms including Dijkstra, A*, and shortestPath
- **Visualization:** Interactive HTML maps for displaying pharmacy locations and routes

## 🚀 Key Features

1. **Advanced Data Management**
   - Downloads and processes OpenStreetMap data for road networks
   - Extracts and stores pharmacy locations from OSM points of interest
   - Implements efficient caching mechanisms to reduce API calls

2. **Graph Database Integration**
   - Uses Neo4j to model intersections as nodes and roads as relationships
   - Implements custom relationship types for pharmacy proximity
   - Optimized indexing for fast query performance

3. **Multiple Search Algorithms**
   - Dijkstra's algorithm with APOC plugin for shortest path calculations
   - A* Search algorithm for optimized pathfinding
   - Fallback shortestPath algorithm for simpler queries
   - Euclidean distance calculation for approximate results

4. **Route Planning**
   - Calculates complete driving directions using OSMnx
   - Provides step-by-step navigation instructions
   - Generates interactive maps for visualization
   - Returns detailed route information including distance and coordinates

5. **Performance Optimizations**
   - Implements caching for frequently accessed data
   - Uses batch processing for large datasets
   - Optimized queries for fast response times
   - Memory-efficient data structures

---

## ⚙️ Quick Start

1. **Clone the Repository**
   ```bash
   git clone https://github.com/YassineElALAMI/GeoSpatial-Pharmacy-Finder.git
   cd GeoSpatial-Pharmacy-Finder
   ```

2. **Set Up Environment**
   ```bash
   python -m venv .venv
   .\.venv\Scripts\activate  # Windows
   pip install -r requirements.txt
   ```

3. **Configure Neo4j**
   - Install Neo4j Desktop from https://neo4j.com/download/
   - Create a new database named `pharmaciegraph`
   - Install APOC plugin from Neo4j Browser
   - Configure connection settings in `.env` file

4. **Run the Application**
   ```bash
   python src/main_insertion.py
   ```
   - The application will prompt to reload OSM data
   - It will calculate and display the nearest pharmacies
   - A detailed route will be generated for the closest pharmacy

---

## 📂 Project Structure

```
GeoSpatial-Pharmacy-Finder/
├── cache/               # Internal JSON cache (auto-created by OSMnx)
│   └── *.json
├── osm_cache/           # Cache for OSM data
│   └── *.json
├── src/                 # Source code directory
│   ├── config.py        # Configuration settings
│   ├── get_location.py  # Location utilities
│   ├── main_insertion.py# Main data insertion logic
│   ├── pharmacie_coords.py # Pharmacy coordinates handling
│   ├── pharmacie_locator.py # Pharmacy search algorithms
│   └── pharmacies_map.html  # Map visualization
├── requirements.txt     # Python dependencies
├── README.md            # Project documentation
├── .env.example         # Environment variables template
├── LICENSE              # License file
├── CHANGELOG.md         # Project changelog
└── pharmacies_map.html   # Main map visualization
```

---

## 📚 Documentation

For detailed documentation:
1. Check the inline comments in source files
2. Review the project structure and file organization
3. Consult the CHANGELOG.md for version history
4. Explore the interactive map visualization

---

## 🔍 Troubleshooting

### Common Issues

1. **Neo4j Connection Failed**
   - Ensure Neo4j Desktop is running
   - Verify database name matches configuration
   - Check APOC plugin is installed
   - Confirm correct connection string in `.env`

2. **OSM Data Download Failed**
   - Check internet connection
   - Verify geographical boundaries
   - Clear cache directory and retry
   - Check OSM API rate limits

3. **Performance Issues**
   - Increase Neo4j heap size if needed
   - Optimize cache settings
   - Consider reducing geographical area
   - Check system resources

---

## 📧 Support

For any questions, issues, or feature requests:

- Open an issue on GitHub
- Email: [yassine.elalami5@usmba.ac.ma](mailto:yassine.elalami5@usmba.ac.ma)
- GitHub: [YassineElALAMI](https://github.com/YassineElALAMI)

---

## 📝 Acknowledgments

- OpenStreetMap community for providing free geospatial data
- Neo4j team for their excellent graph database technology
- All contributors who have helped improve this project
- Special thanks to the Big Data Analytics course instructors

---

## 📝 Changelog

For a detailed list of changes and updates, see [CHANGELOG.md](CHANGELOG.md).
