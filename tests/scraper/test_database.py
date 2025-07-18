"""
Tests for database operations in scraper.py
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from scraper import init_servers, save_results
from models.models import Server, PlayerCount, Player


class TestInitServers:
    """Test server initialization in database"""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session"""
        return Mock()

    def test_init_servers_creates_new_servers(self, mock_db_session):
        """Test that new servers are created in database"""
        servers_config = [
            {"id": "new1", "name": "New Server 1", "ip": "127.0.0.1", "port": 25565},
            {"id": "new2", "name": "New Server 2", "ip": "127.0.0.1", "port": 25566},
        ]

        # Mock that no servers exist
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        with patch("scraper.Server") as mock_server_class:
            init_servers(mock_db_session, servers_config)

            # Should create 2 servers
            assert mock_server_class.call_count == 2

            # Check first server creation
            first_call = mock_server_class.call_args_list[0]
            assert first_call.kwargs["id"] == "new1"
            assert first_call.kwargs["name"] == "New Server 1"
            assert first_call.kwargs["ip"] == "127.0.0.1"
            assert first_call.kwargs["port"] == 25565

            # Should add both servers to session
            assert mock_db_session.add.call_count == 2
            mock_db_session.commit.assert_called_once()

    def test_init_servers_skips_existing_servers(self, mock_db_session):
        """Test that existing servers are not recreated"""
        servers_config = [
            {
                "id": "existing1",
                "name": "Existing Server 1",
                "ip": "127.0.0.1",
                "port": 25565,
            }
        ]

        # Mock that server already exists
        existing_server = Mock()
        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            existing_server
        )

        with patch("scraper.Server") as mock_server_class:
            init_servers(mock_db_session, servers_config)

            # Should not create any new servers
            mock_server_class.assert_not_called()
            mock_db_session.add.assert_not_called()
            mock_db_session.commit.assert_called_once()

    def test_init_servers_mixed_new_and_existing(self, mock_db_session):
        """Test initialization with mix of new and existing servers"""
        servers_config = [
            {
                "id": "existing",
                "name": "Existing Server",
                "ip": "127.0.0.1",
                "port": 25565,
            },
            {"id": "new", "name": "New Server", "ip": "127.0.0.1", "port": 25566},
        ]

        def mock_query_result(server_id):
            if "existing" in str(server_id):
                return Mock()  # Existing server
            return None  # New server

        # Mock query chain to return different results
        mock_filter = Mock()
        mock_filter.first.side_effect = [Mock(), None]  # First exists, second doesn't
        mock_db_session.query.return_value.filter.return_value = mock_filter

        with patch("scraper.Server") as mock_server_class:
            init_servers(mock_db_session, servers_config)

            # Should create only 1 server (the new one)
            assert mock_server_class.call_count == 1
            assert mock_db_session.add.call_count == 1
            mock_db_session.commit.assert_called_once()


class TestSaveResults:
    """Test saving scraping results to database"""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session"""
        return Mock()

    def test_save_results_successful_entries_only(self, mock_db_session):
        """Test that only successful results are saved"""
        results = [
            {
                "server_id": "server1",
                "player_count": 3,
                "players": ["Player1"],
                "success": True,
            },
            {
                "server_id": "server2",
                "player_count": 0,
                "players": [],
                "success": False,
            },  # Should skip
            {
                "server_id": "server3",
                "player_count": 2,
                "players": ["Player2"],
                "success": True,
            },
        ]

        # Mock that no players exist yet
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        with patch("scraper.PlayerCount") as mock_pc_class:
            with patch("scraper.Player") as mock_player_class:
                with patch("scraper.datetime") as mock_datetime:
                    mock_datetime.utcnow.return_value = datetime(2024, 1, 1, 12, 0, 0)

                    save_results(mock_db_session, results)

                    # Should create 2 PlayerCount entries (only successful ones)
                    assert mock_pc_class.call_count == 2

                    # Should create 2 Player entries (Player1 and Player2)
                    assert mock_player_class.call_count == 2

                    mock_db_session.commit.assert_called_once()

    def test_save_results_reuses_existing_players(self, mock_db_session):
        """Test that existing players are reused, not recreated"""
        results = [
            {
                "server_id": "server1",
                "player_count": 2,
                "players": ["ExistingPlayer", "NewPlayer"],
                "success": True,
            }
        ]

        existing_player = Mock()
        existing_player.username = "ExistingPlayer"

        def mock_player_lookup(filter_arg):
            # Return existing player for first lookup, None for second
            if hasattr(mock_player_lookup, "call_count"):
                mock_player_lookup.call_count += 1
                return None
            else:
                mock_player_lookup.call_count = 1
                return existing_player

        mock_db_session.query.return_value.filter.return_value.first.side_effect = [
            existing_player,
            None,
        ]

        mock_player_count = Mock()
        mock_player_count.players = []

        with patch("scraper.PlayerCount", return_value=mock_player_count):
            with patch("scraper.Player") as mock_player_class:
                save_results(mock_db_session, results)

                # Should only create 1 new Player (NewPlayer), not ExistingPlayer
                assert mock_player_class.call_count == 1

                # Check that the new player was created with correct username
                mock_player_class.assert_called_with(username="NewPlayer")

    def test_save_results_associates_players_with_snapshot(self, mock_db_session):
        """Test that players are properly associated with player count snapshots"""
        results = [
            {
                "server_id": "server1",
                "player_count": 1,
                "players": ["TestPlayer"],
                "success": True,
            }
        ]

        # Mock that player doesn't exist
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        mock_player_count = Mock()
        mock_player_count.players = []
        mock_player = Mock()

        with patch("scraper.PlayerCount", return_value=mock_player_count):
            with patch("scraper.Player", return_value=mock_player):
                save_results(mock_db_session, results)

                # Verify the player was associated with the snapshot
                assert mock_player in mock_player_count.players

    def test_save_results_with_no_players(self, mock_db_session):
        """Test saving results when no players are online"""
        results = [
            {"server_id": "server1", "player_count": 0, "players": [], "success": True}
        ]

        mock_player_count = Mock()
        mock_player_count.players = []

        with patch(
            "scraper.PlayerCount", return_value=mock_player_count
        ) as mock_pc_class:
            with patch("scraper.Player") as mock_player_class:
                save_results(mock_db_session, results)

                # Should create 1 PlayerCount entry
                assert mock_pc_class.call_count == 1

                # Should not create any Player entries
                mock_player_class.assert_not_called()

                # Should still commit the transaction
                mock_db_session.commit.assert_called_once()

    def test_save_results_empty_list(self, mock_db_session):
        """Test saving empty results list"""
        results = []

        with patch("scraper.PlayerCount") as mock_pc_class:
            with patch("scraper.Player") as mock_player_class:
                save_results(mock_db_session, results)

                # Should not create anything
                mock_pc_class.assert_not_called()
                mock_player_class.assert_not_called()

                # Should still commit
                mock_db_session.commit.assert_called_once()

    def test_save_results_timestamp_consistency(self, mock_db_session):
        """Test that all entries use the same timestamp"""
        results = [
            {"server_id": "server1", "player_count": 1, "players": [], "success": True},
            {"server_id": "server2", "player_count": 2, "players": [], "success": True},
        ]

        mock_player_count1 = Mock()
        mock_player_count1.players = []
        mock_player_count2 = Mock()
        mock_player_count2.players = []

        with patch(
            "scraper.PlayerCount", side_effect=[mock_player_count1, mock_player_count2]
        ) as mock_pc_class:
            with patch("scraper.datetime") as mock_datetime:
                fixed_time = datetime(2024, 1, 1, 12, 0, 0)
                mock_datetime.utcnow.return_value = fixed_time

                save_results(mock_db_session, results)

                # Check that both PlayerCount objects were created with same timestamp
                assert mock_pc_class.call_count == 2

                # Verify timestamp was passed to both
                call_args_list = mock_pc_class.call_args_list
                for call_args in call_args_list:
                    assert call_args.kwargs["timestamp"] == fixed_time


class TestDatabaseErrorHandling:
    """Test database error scenarios"""

    @pytest.fixture
    def mock_db_session(self):
        return Mock()

    def test_init_servers_database_error(self, mock_db_session):
        """Test init_servers handles database errors gracefully"""
        servers_config = [
            {"id": "test", "name": "Test Server", "ip": "127.0.0.1", "port": 25565}
        ]

        # Mock database error on commit
        mock_db_session.commit.side_effect = Exception("Database connection failed")
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        with patch("scraper.Server"):
            with pytest.raises(Exception, match="Database connection failed"):
                init_servers(mock_db_session, servers_config)

    def test_save_results_database_error_on_commit(self, mock_db_session):
        """Test save_results handles database errors on commit"""
        results = [
            {"server_id": "server1", "player_count": 1, "players": [], "success": True}
        ]

        # Mock database error on commit
        mock_db_session.commit.side_effect = Exception("Commit failed")
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        mock_player_count = Mock()
        mock_player_count.players = []

        with patch("scraper.PlayerCount", return_value=mock_player_count):
            with pytest.raises(Exception, match="Commit failed"):
                save_results(mock_db_session, results)

    def test_save_results_database_error_on_flush(self, mock_db_session):
        """Test save_results handles database errors on flush"""
        results = [
            {
                "server_id": "server1",
                "player_count": 1,
                "players": ["Player1"],
                "success": True,
            }
        ]

        # Mock database error on flush
        mock_db_session.flush.side_effect = Exception("Flush failed")
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        mock_player_count = Mock()
        mock_player_count.players = []

        with patch("scraper.PlayerCount", return_value=mock_player_count):
            with patch("scraper.Player"):
                with pytest.raises(Exception, match="Flush failed"):
                    save_results(mock_db_session, results)


class TestPlayerHandling:
    """Test specific player handling scenarios"""

    @pytest.fixture
    def mock_db_session(self):
        return Mock()

    def test_save_results_duplicate_players_in_result(self, mock_db_session):
        """Test handling of duplicate players in the same result"""
        results = [
            {
                "server_id": "server1",
                "player_count": 2,
                "players": ["Player1", "Player1"],
                "success": True,
            }
        ]

        # Mock that player doesn't exist initially
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        mock_player_count = Mock()
        mock_player_count.players = []
        mock_player = Mock()

        with patch("scraper.PlayerCount", return_value=mock_player_count):
            with patch("scraper.Player", return_value=mock_player) as mock_player_class:
                save_results(mock_db_session, results)

                # Should handle duplicates (might create player twice or handle it)
                # The exact behavior depends on implementation
                assert mock_player_class.call_count >= 1

    def test_save_results_case_sensitive_usernames(self, mock_db_session):
        """Test that usernames are handled in a case-sensitive manner"""
        results = [
            {
                "server_id": "server1",
                "player_count": 2,
                "players": ["Player1", "player1"],
                "success": True,
            }
        ]

        # Mock that neither player exists
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        mock_player_count = Mock()
        mock_player_count.players = []

        with patch("scraper.PlayerCount", return_value=mock_player_count):
            with patch("scraper.Player") as mock_player_class:
                save_results(mock_db_session, results)

                # Should create 2 separate players (case sensitive)
                assert mock_player_class.call_count == 2

                # Verify both usernames were used
                call_args_list = mock_player_class.call_args_list
                usernames = [call.kwargs["username"] for call in call_args_list]
                assert "Player1" in usernames
                assert "player1" in usernames


# Simple test runner
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
