"""
Pytest configuration file for shared fixtures and test setup.
"""
import sys
from pathlib import Path

# Add the src directory to the Python path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# You can add more shared fixtures here that can be used across all test files
# For example, if you want to share the database fixtures across multiple test files:

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.models.database import Base


@pytest.fixture(scope="session")
def engine():
    """Create a shared in-memory SQLite engine for the test session"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture(scope="function")
def db_session(engine):
    """Create a new database session for each test function"""
    connection = engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection)
    session = Session()
    
    yield session
    
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def sample_servers():
    """Provide sample server data for testing"""
    return [
        {
            "id": "mce",
            "name": "MC Eternal",
            "ip": "calmingstorm.net",
            "port": 25580
        },
        {
            "id": "gtnh",
            "name": "GregTech: New Horizons",
            "ip": "calmingstorm.net",
            "port": 25567
        },
        {
            "id": "tnp",
            "name": "TNP Limitless 8",
            "ip": "calmingstorm.net",
            "port": 25568
        }
    ]


@pytest.fixture
def sample_players():
    """Provide sample player names for testing"""
    return ["Player1", "Player2", "Player3", "TestUser", "Admin"]