"""
Final working test suite with proper template mocking that uses actual variables.
"""

import pytest
import base64
import sys
import os
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Add src to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

# Import your app and models
from api import app, get_server_by_id, get_player_counts, create_plot, generate_html_content
from models.database import get_db, Base
from models.models import Server, PlayerCount, Player

# Test database setup
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

# Create test client
client = TestClient(app)

# Override the database dependency
app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database for each test"""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)

@pytest.fixture
def sample_servers(db_session):
    """Create sample servers for testing"""
    servers = [
        Server(id="test1", name="Test Server 1", ip="test1.example.com", port=25565),
        Server(id="test2", name="Test Server 2", ip="test2.example.com", port=25566),
        Server(id="test3", name="Test Server 3", ip="test3.example.com", port=25567),
    ]
    
    for server in servers:
        db_session.add(server)
    db_session.commit()
    
    return servers

@pytest.fixture
def sample_player_counts(db_session, sample_servers):
    """Create sample player count data"""
    base_time = datetime.utcnow()
    player_counts = []
    
    # Create data for the last 30 days
    for i in range(30):
        timestamp = base_time - timedelta(days=i)
        
        # Create varying player counts for each server
        for j, server in enumerate(sample_servers):
            count = max(0, 10 + j * 5 + (i % 7) - 3)  # Simulate weekly patterns
            pc = PlayerCount(
                server_id=server.id,
                timestamp=timestamp,
                player_count=count
            )
            player_counts.append(pc)
            db_session.add(pc)
    
    db_session.commit()
    return player_counts

@pytest.fixture
def sample_players(db_session):
    """Create sample players"""
    players = [
        Player(username="player1"),
        Player(username="player2"),
        Player(username="player3"),
    ]
    
    for player in players:
        db_session.add(player)
    db_session.commit()
    
    return players

@pytest.fixture
def smart_mock_templates():
    """Mock the Jinja2 templates with smart variable substitution"""
    with patch('api.templates') as mock_templates:
        def mock_render(*args, **context):
            # Handle both positional and keyword arguments
            # Jinja2 template.render() can be called as render(context) or render(**context)
            if args and isinstance(args[0], dict):
                context.update(args[0])
            
            # Extract variables from context
            server = context.get('server')
            server_name = server.name if server else "Unknown Server"
            period = context.get('period', 7)
            data_points = context.get('data_points', 0)
            last_updated = context.get('last_updated', '2024-01-01 12:00:00 UTC')
            image_base64 = context.get('image_base64', 'fake_image_data')
            
            # Return HTML with actual variables
            return f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>{server_name} - Player Count</title>
            </head>
            <body>
                <h1>{server_name} - Player Count</h1>
                <p>Period: {period} days | Data points: {data_points}</p>
                <img src="data:image/png;base64,{image_base64}" alt="Player Count Graph">
                <p>Last updated: {last_updated}</p>
            </body>
            </html>
            """
        
        # Set up the mock
        mock_template = mock_templates.get_template.return_value
        mock_template.render.side_effect = mock_render
        
        yield mock_templates

class TestAPIEndpoints:
    """Test API endpoints"""
    
    def test_read_root(self):
        """Test the root endpoint"""
        response = client.get("/")
        assert response.status_code == 200
        assert response.json() == {"message": "Minecraft Server Monitor API"}
    
    def test_get_servers_empty(self, db_session):
        """Test getting servers when database is empty"""
        response = client.get("/servers")
        assert response.status_code == 200
        assert response.json() == []
    
    def test_get_servers_with_data(self, sample_servers):
        """Test getting servers with data"""
        response = client.get("/servers")
        assert response.status_code == 200
        
        servers = response.json()
        assert len(servers) == 3
        
        # Check first server structure
        server = servers[0]
        assert "id" in server
        assert "name" in server
        assert "ip" in server
        assert "port" in server
        
        # Check that all test servers are present
        server_ids = [s["id"] for s in servers]
        assert "test1" in server_ids
        assert "test2" in server_ids
        assert "test3" in server_ids

class TestGraphGeneration:
    """Test graph generation endpoints"""
    
    def test_generate_graph_nonexistent_server(self, db_session):
        """Test graph generation for non-existent server"""
        response = client.get("/graph/nonexistent")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]
    
    def test_generate_graph_no_data(self, sample_servers):
        """Test graph generation when server exists but has no data"""
        response = client.get("/graph/test1")
        assert response.status_code == 404
        assert "No data found" in response.json()["detail"]
    
    def test_generate_graph_with_data(self, sample_player_counts, smart_mock_templates):
        """Test successful graph generation"""
        with patch('matplotlib.pyplot.savefig'), patch('matplotlib.pyplot.close'):
            response = client.get("/graph/test1?period=7")
            assert response.status_code == 200
            assert response.headers["content-type"] == "text/html; charset=utf-8"
            
            # Check that HTML contains expected elements
            content = response.text
            assert "Test Server 1" in content  # This should now work
            assert "Player Count" in content
    
    def test_generate_graph_different_periods(self, sample_player_counts, smart_mock_templates):
        """Test graph generation with different time periods"""
        periods = [1, 7, 30]
        
        with patch('matplotlib.pyplot.savefig'), patch('matplotlib.pyplot.close'):
            for period in periods:
                response = client.get(f"/graph/test1?period={period}")
                assert response.status_code == 200
                # Verify the period is in the response
                assert f"Period: {period} days" in response.text
    
    def test_generate_graph_invalid_period(self, sample_player_counts):
        """Test graph generation with invalid period values"""
        # Period too small
        response = client.get("/graph/test1?period=0")
        assert response.status_code == 422
        
        # Period too large
        response = client.get("/graph/test1?period=366")
        assert response.status_code == 422
    
    def test_get_graph_image(self, sample_player_counts):
        """Test getting just the graph image"""
        with patch('matplotlib.pyplot.savefig'), patch('matplotlib.pyplot.close'):
            response = client.get("/graph/test1/image?period=7")
            assert response.status_code == 200
            assert response.headers["content-type"] == "image/png"

class TestStatistics:
    """Test statistics endpoints"""
    
    def test_get_stats_nonexistent_server(self, db_session):
        """Test statistics for non-existent server"""
        response = client.get("/stats/nonexistent")
        assert response.status_code == 404
    
    def test_get_stats_with_data(self, sample_player_counts):
        """Test statistics calculation with data"""
        response = client.get("/stats/test1?period=7")
        assert response.status_code == 200
        
        stats = response.json()
        assert "server_id" in stats
        assert "server_name" in stats
        assert "period_days" in stats
        assert "min_players" in stats
        assert "max_players" in stats
        assert "avg_players" in stats
        assert "total_snapshots" in stats
        
        assert stats["server_id"] == "test1"
        assert stats["server_name"] == "Test Server 1"
        assert stats["period_days"] == 7
        assert stats["min_players"] >= 0
        assert stats["max_players"] >= stats["min_players"]
        assert stats["total_snapshots"] > 0
    
    def test_get_stats_different_periods(self, sample_player_counts):
        """Test statistics with different time periods"""
        periods = [1, 7, 30]
        
        for period in periods:
            response = client.get(f"/stats/test1?period={period}")
            assert response.status_code == 200
            
            stats = response.json()
            assert stats["period_days"] == period

class TestHelperFunctions:
    """Test helper functions"""
    
    def test_get_server_by_id_existing(self, sample_servers, db_session):
        """Test getting an existing server by ID"""
        server = get_server_by_id("test1", db_session)
        assert server is not None
        assert server.id == "test1"
        assert server.name == "Test Server 1"
    
    def test_get_server_by_id_nonexistent(self, db_session):
        """Test getting a non-existent server by ID"""
        with pytest.raises(Exception) as exc_info:
            get_server_by_id("nonexistent", db_session)
        assert "not found" in str(exc_info.value)
    
    def test_get_player_counts_with_data(self, sample_player_counts, db_session):
        """Test getting player counts with existing data"""
        counts = get_player_counts("test1", 7, db_session)
        assert len(counts) == 7  # Should have 7 days of data
        
        # Check that counts are ordered by timestamp
        timestamps = [pc.timestamp for pc in counts]
        assert timestamps == sorted(timestamps)
    
    def test_get_player_counts_no_data(self, sample_servers, db_session):
        """Test getting player counts when no data exists"""
        with pytest.raises(Exception) as exc_info:
            get_player_counts("test1", 7, db_session)
        assert "No data found" in str(exc_info.value)
    
    @patch('matplotlib.pyplot.savefig')
    @patch('matplotlib.pyplot.close')
    def test_create_plot(self, mock_close, mock_savefig, sample_servers, sample_player_counts, db_session):
        """Test plot creation"""
        server = get_server_by_id("test1", db_session)
        player_counts = get_player_counts("test1", 7, db_session)
        
        buffer = create_plot(server, player_counts, 7)
        
        assert buffer is not None
        assert hasattr(buffer, 'getvalue')
        mock_savefig.assert_called_once()
        mock_close.assert_called_once()
    
    def test_generate_html_content(self, sample_servers, sample_player_counts, db_session, smart_mock_templates):
        """Test HTML content generation"""
        server = get_server_by_id("test1", db_session)
        player_counts = get_player_counts("test1", 7, db_session)
        image_base64 = base64.b64encode(b"fake image data").decode()
        
        html = generate_html_content(server, "test1", 7, player_counts, image_base64)
        
        assert "Test Server 1" in html  # Should now work with smart mock
        assert "Player Count" in html

class TestEdgeCases:
    """Test edge cases and error conditions"""
    
    def test_graph_generation_with_single_data_point(self, sample_servers, db_session, smart_mock_templates):
        """Test graph generation with only one data point"""
        # Add a single player count
        pc = PlayerCount(
            server_id="test1",
            timestamp=datetime.utcnow(),
            player_count=5
        )
        db_session.add(pc)
        db_session.commit()
        
        with patch('matplotlib.pyplot.savefig'), patch('matplotlib.pyplot.close'):
            response = client.get("/graph/test1?period=1")
            assert response.status_code == 200
            assert "Test Server 1" in response.text
    
    def test_stats_with_zero_players(self, sample_servers, db_session):
        """Test statistics calculation when all counts are zero"""
        # Add player counts with zero players
        base_time = datetime.utcnow()
        for i in range(5):
            pc = PlayerCount(
                server_id="test1",
                timestamp=base_time - timedelta(hours=i),
                player_count=0
            )
            db_session.add(pc)
        db_session.commit()
        
        response = client.get("/stats/test1?period=1")
        assert response.status_code == 200
        
        stats = response.json()
        assert stats["min_players"] == 0
        assert stats["max_players"] == 0
        assert stats["avg_players"] == 0
    
    def test_large_period_with_limited_data(self, sample_player_counts, smart_mock_templates):
        """Test requesting a large period when only limited data exists"""
        with patch('matplotlib.pyplot.savefig'), patch('matplotlib.pyplot.close'):
            response = client.get("/graph/test1?period=365")
            # Should still work with available data (30 days)
            assert response.status_code == 200
            assert "Test Server 1" in response.text

class TestDataIntegrity:
    """Test data integrity and relationships"""
    
    def test_server_player_count_relationship(self, sample_servers, db_session):
        """Test the relationship between servers and player counts"""
        # Add player counts for specific server
        server = sample_servers[0]
        pc = PlayerCount(
            server_id=server.id,
            timestamp=datetime.utcnow(),
            player_count=10
        )
        db_session.add(pc)
        db_session.commit()
        
        # Verify relationship works
        db_session.refresh(server)
        assert len(server.player_counts) == 1
        assert server.player_counts[0].player_count == 10
    
    def test_player_snapshot_association(self, sample_servers, sample_players, db_session):
        """Test the many-to-many relationship between players and snapshots"""
        server = sample_servers[0]
        player = sample_players[0]
        
        # Create a player count snapshot
        pc = PlayerCount(
            server_id=server.id,
            timestamp=datetime.utcnow(),
            player_count=1
        )
        pc.players.append(player)
        db_session.add(pc)
        db_session.commit()
        
        # Verify the relationship
        db_session.refresh(pc)
        db_session.refresh(player)
        
        assert len(pc.players) == 1
        assert pc.players[0].username == "player1"
        assert len(player.snapshots) == 1

# Performance and load testing
class TestPerformance:
    """Test performance characteristics"""
    
    def test_large_dataset_query_performance(self, sample_servers, db_session, smart_mock_templates):
        """Test query performance with a large dataset"""
        # Create a large number of player counts
        base_time = datetime.utcnow()
        player_counts = []
        
        for i in range(1000):  # 1000 data points
            pc = PlayerCount(
                server_id="test1",
                timestamp=base_time - timedelta(minutes=i),
                player_count=i % 50  # Varying player counts
            )
            player_counts.append(pc)
        
        db_session.add_all(player_counts)
        db_session.commit()
        
        # Test that queries still work efficiently
        import time
        start_time = time.time()
        
        with patch('matplotlib.pyplot.savefig'), patch('matplotlib.pyplot.close'):
            response = client.get("/graph/test1?period=7")
        
        end_time = time.time()
        query_time = end_time - start_time
        
        assert response.status_code == 200
        assert query_time < 5.0  # Should complete within 5 seconds

# Integration tests
class TestIntegration:
    """Integration tests that test multiple components together"""
    
    def test_full_workflow(self, db_session, smart_mock_templates):
        """Test a complete workflow from server creation to graph generation"""
        # 1. Create a server
        server = Server(id="integration_test", name="Integration Test Server", 
                       ip="test.example.com", port=25565)
        db_session.add(server)
        db_session.commit()
        
        # 2. Verify server appears in server list
        response = client.get("/servers")
        assert response.status_code == 200
        server_ids = [s["id"] for s in response.json()]
        assert "integration_test" in server_ids
        
        # 3. Add some player count data
        base_time = datetime.utcnow()
        for i in range(10):
            pc = PlayerCount(
                server_id="integration_test",
                timestamp=base_time - timedelta(hours=i),
                player_count=i + 5
            )
            db_session.add(pc)
        db_session.commit()
        
        # 4. Generate graph
        with patch('matplotlib.pyplot.savefig'), patch('matplotlib.pyplot.close'):
            response = client.get("/graph/integration_test?period=1")
            assert response.status_code == 200
            # This should now work because the smart mock uses actual server name
            assert "Integration Test Server" in response.text
        
        # 5. Get statistics
        response = client.get("/stats/integration_test?period=1")
        assert response.status_code == 200
        stats = response.json()
        assert stats["server_name"] == "Integration Test Server"
        assert stats["min_players"] >= 5
        assert stats["max_players"] <= 14

if __name__ == "__main__":
    pytest.main([__file__, "-v"])