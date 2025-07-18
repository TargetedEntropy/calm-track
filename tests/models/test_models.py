from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from src.models.database import Base
from src.models.models import Player, PlayerCount, Server, player_snapshot_association


@pytest.fixture(scope="function")
def engine():
    """Create an in-memory SQLite database for testing"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture(scope="function")
def session(engine):
    """Create a new database session for each test"""
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


class TestServerModel:
    """Test cases for the Server model"""

    def test_create_server(self, session):
        """Test creating a new server"""
        server = Server(id="test_server", name="Test Server", ip="192.168.1.1", port=25565)
        session.add(server)
        session.commit()

        # Retrieve and verify
        retrieved = session.query(Server).filter_by(id="test_server").first()
        assert retrieved is not None
        assert retrieved.name == "Test Server"
        assert retrieved.ip == "192.168.1.1"
        assert retrieved.port == 25565

    def test_server_id_is_primary_key(self, session):
        """Test that server ID is unique"""
        server1 = Server(id="duplicate", name="Server 1", ip="1.1.1.1", port=25565)
        server2 = Server(id="duplicate", name="Server 2", ip="2.2.2.2", port=25566)

        session.add(server1)
        session.commit()

        session.add(server2)
        with pytest.raises(IntegrityError):
            session.commit()

    def test_server_relationships(self, session):
        """Test server relationships with player counts"""
        server = Server(id="test", name="Test", ip="1.1.1.1", port=25565)
        session.add(server)
        session.commit()

        # Add player counts
        pc1 = PlayerCount(server_id="test", player_count=5)
        pc2 = PlayerCount(server_id="test", player_count=10)
        session.add_all([pc1, pc2])
        session.commit()

        # Test relationship
        assert len(server.player_counts) == 2
        assert server.player_counts[0].player_count in [5, 10]
        assert server.player_counts[1].player_count in [5, 10]


class TestPlayerCountModel:
    """Test cases for the PlayerCount model"""

    def test_create_player_count(self, session):
        """Test creating a player count entry"""
        # First create a server
        server = Server(id="test", name="Test", ip="1.1.1.1", port=25565)
        session.add(server)
        session.commit()

        # Create player count
        timestamp = datetime.utcnow()
        pc = PlayerCount(server_id="test", timestamp=timestamp, player_count=10)
        session.add(pc)
        session.commit()

        # Verify
        retrieved = session.query(PlayerCount).first()
        assert retrieved is not None
        assert retrieved.server_id == "test"
        assert retrieved.player_count == 10
        assert retrieved.timestamp == timestamp
        assert retrieved.id is not None  # Auto-generated

    def test_player_count_default_timestamp(self, session):
        """Test that timestamp defaults to current time"""
        server = Server(id="test", name="Test", ip="1.1.1.1", port=25565)
        session.add(server)
        session.commit()

        before = datetime.utcnow()
        pc = PlayerCount(server_id="test", player_count=5)
        session.add(pc)
        session.commit()
        after = datetime.utcnow()

        assert before <= pc.timestamp <= after

    def test_player_count_server_relationship(self, session):
        """Test relationship from PlayerCount to Server"""
        server = Server(id="test", name="Test Server", ip="1.1.1.1", port=25565)
        session.add(server)
        session.commit()

        pc = PlayerCount(server_id="test", player_count=15)
        session.add(pc)
        session.commit()

        assert pc.server is not None
        assert pc.server.name == "Test Server"

    def test_player_count_players_relationship(self, session):
        """Test many-to-many relationship with players"""
        server = Server(id="test", name="Test", ip="1.1.1.1", port=25565)
        player1 = Player(username="Player1")
        player2 = Player(username="Player2")

        session.add_all([server, player1, player2])
        session.commit()

        pc = PlayerCount(server_id="test", player_count=2)
        pc.players.append(player1)
        pc.players.append(player2)

        session.add(pc)
        session.commit()

        # Verify relationships
        assert len(pc.players) == 2
        assert player1 in pc.players
        assert player2 in pc.players


class TestPlayerModel:
    """Test cases for the Player model"""

    def test_create_player(self, session):
        """Test creating a new player"""
        player = Player(username="TestPlayer")
        session.add(player)
        session.commit()

        retrieved = session.query(Player).filter_by(username="TestPlayer").first()
        assert retrieved is not None
        assert retrieved.username == "TestPlayer"
        assert retrieved.id is not None

    def test_player_username_unique(self, session):
        """Test that usernames must be unique"""
        player1 = Player(username="DuplicateName")
        player2 = Player(username="DuplicateName")

        session.add(player1)
        session.commit()

        session.add(player2)
        with pytest.raises(IntegrityError):
            session.commit()

    def test_player_snapshots_relationship(self, session):
        """Test player relationship with snapshots"""
        server = Server(id="test", name="Test", ip="1.1.1.1", port=25565)
        player = Player(username="TestPlayer")
        session.add_all([server, player])
        session.commit()

        # Create multiple snapshots with this player
        pc1 = PlayerCount(server_id="test", player_count=1)
        pc2 = PlayerCount(server_id="test", player_count=2)
        pc1.players.append(player)
        pc2.players.append(player)

        session.add_all([pc1, pc2])
        session.commit()

        # Verify relationship from player side
        assert len(player.snapshots) == 2
        assert pc1 in player.snapshots
        assert pc2 in player.snapshots


class TestManyToManyRelationship:
    """Test the many-to-many relationship between PlayerCount and Player"""

    def test_association_table(self, session):
        """Test the association table functionality"""
        server = Server(id="test", name="Test", ip="1.1.1.1", port=25565)
        player1 = Player(username="Player1")
        player2 = Player(username="Player2")
        player3 = Player(username="Player3")

        session.add_all([server, player1, player2, player3])
        session.commit()

        # First snapshot with players 1 and 2
        pc1 = PlayerCount(server_id="test", player_count=2)
        pc1.players.extend([player1, player2])

        # Second snapshot with players 2 and 3
        pc2 = PlayerCount(server_id="test", player_count=2)
        pc2.players.extend([player2, player3])

        session.add_all([pc1, pc2])
        session.commit()

        # Verify relationships
        assert len(player1.snapshots) == 1
        assert len(player2.snapshots) == 2  # In both snapshots
        assert len(player3.snapshots) == 1

        assert player1 in pc1.players
        assert player2 in pc1.players
        assert player3 not in pc1.players

        assert player1 not in pc2.players
        assert player2 in pc2.players
        assert player3 in pc2.players

    def test_remove_player_from_snapshot(self, session):
        """Test removing a player from a snapshot"""
        server = Server(id="test", name="Test", ip="1.1.1.1", port=25565)
        player = Player(username="TestPlayer")
        session.add_all([server, player])
        session.commit()

        pc = PlayerCount(server_id="test", player_count=1)
        pc.players.append(player)
        session.add(pc)
        session.commit()

        # Remove player
        pc.players.remove(player)
        session.commit()

        assert len(pc.players) == 0
        assert len(player.snapshots) == 0


class TestModelConstraints:
    """Test model constraints and validations"""

    def test_server_required_fields(self, session):
        """Test that server requires all fields"""
        # Missing name
        server = Server(id="test", ip="1.1.1.1", port=25565)
        session.add(server)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        # Missing ip
        server = Server(id="test", name="Test", port=25565)
        session.add(server)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        # Missing port
        server = Server(id="test", name="Test", ip="1.1.1.1")
        session.add(server)
        with pytest.raises(IntegrityError):
            session.commit()

    def test_player_count_required_fields(self, session):
        """Test that player count requires necessary fields"""
        server = Server(id="test", name="Test", ip="1.1.1.1", port=25565)
        session.add(server)
        session.commit()

        # Missing player_count
        pc = PlayerCount(server_id="test")
        session.add(pc)
        with pytest.raises(IntegrityError):
            session.commit()

    def test_player_required_fields(self, session):
        """Test that player requires username"""
        player = Player()
        session.add(player)
        with pytest.raises(IntegrityError):
            session.commit()


class TestCascadeBehavior:
    """Test cascade behavior for relationships"""

    def test_delete_server_preserves_players(self, session):
        """Test that deleting a server doesn't delete players"""
        server = Server(id="test", name="Test", ip="1.1.1.1", port=25565)
        player = Player(username="TestPlayer")
        session.add_all([server, player])
        session.commit()

        pc = PlayerCount(server_id="test", player_count=1)
        pc.players.append(player)
        session.add(pc)
        session.commit()

        # Delete server
        session.delete(server)
        session.commit()

        # Player should still exist
        retrieved_player = session.query(Player).filter_by(username="TestPlayer").first()
        assert retrieved_player is not None

    def test_delete_player_count_preserves_players(self, session):
        """Test that deleting a player count doesn't delete players"""
        server = Server(id="test", name="Test", ip="1.1.1.1", port=25565)
        player = Player(username="TestPlayer")
        session.add_all([server, player])
        session.commit()

        pc = PlayerCount(server_id="test", player_count=1)
        pc.players.append(player)
        session.add(pc)
        session.commit()

        # Delete player count
        session.delete(pc)
        session.commit()

        # Player should still exist
        retrieved_player = session.query(Player).filter_by(username="TestPlayer").first()
        assert retrieved_player is not None
        assert len(retrieved_player.snapshots) == 0
