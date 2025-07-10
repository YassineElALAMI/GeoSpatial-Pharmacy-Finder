import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Neo4j Configuration
NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'test1234')
NEO4J_DATABASE = os.getenv('NEO4J_DATABASE', 'pharmaciegraph')

# Logging Configuration
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# Application Settings
DEFAULT_PLACE = os.getenv('DEFAULT_PLACE', 'Rabat')
MAX_RESULTS = int(os.getenv('MAX_RESULTS', '5'))

# Cache Settings
CACHE_ENABLED = os.getenv('CACHE_ENABLED', 'True').lower() == 'true'
CACHE_DIR = os.getenv('CACHE_DIR', 'cache')
OSM_CACHE_DIR = os.getenv('OSM_CACHE_DIR', 'osm_cache')
