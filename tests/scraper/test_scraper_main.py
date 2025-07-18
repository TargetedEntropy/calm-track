import asyncio
import fcntl
import json
import os
import pytest
from datetime import datetime
from unittest.mock import Mock, patch, mock_open, MagicMock, AsyncMock
from sqlalchemy.orm import Session

# Import the functions to test
import sys
sys.path.append('src')
from scraper import (
    main, acquire_lock, release_lock, load_servers, init_servers,
    query_server, scrape_all_servers, save_results
)
from models.models import Server, PlayerCount, Player


class TestScraperMain:
    """Test cases for the main scraper function and its components"""

    @pytest.fixture
    def mock_servers_config(self):
        """Sample server configuration for testing"""
        return [
            {
                "id": "test1",
                "name": "Test Server 1",
                "ip": "test1.example.com",
                "port": 25565
            },
            {
                "id": "test2", 
                "name": "Test Server 2",
                "ip": "test2.example.com",
                "port": 25566
            }
        ]

    @pytest.fixture
    def mock_query_results(self):
        """Sample query results for testing"""
        return [
            {
                "server_id": "test1",
                "player_count": 5,
                "players": ["player1", "player2", "player3", "player4", "player5"],
                "success": True
            },
            {
                "server_id": "test2",
                "player_count": 0,
                "players": [],
                "success": True
            }
        ]

    @pytest.fixture
    def mock_db_session(self):
        """Mock database session"""
        session = Mock(spec=Session)
        session.query.return_value.filter.return_value.first.return_value = None
        session.add = Mock()
        session.commit = Mock()
        session.flush = Mock()
        session.close = Mock()
        return session

    @pytest.fixture
    def mock_lock_file(self):
        """Mock lock file for testing"""
        lock_file = Mock()
        return lock_file

    @patch('scraper.acquire_lock')
    @patch('scraper.release_lock')
    @patch('scraper.Base.metadata.create_all')
    @patch('scraper.load_servers')
    @patch('scraper.SessionLocal')
    @patch('scraper.init_servers')
    @patch('scraper.scrape_all_servers')
    @patch('scraper.save_results')
    @pytest.mark.asyncio
    async def test_main_successful_execution(
        self, mock_save_results, mock_scrape_all_servers, mock_init_servers,
        mock_session_local, mock_load_servers, mock_create_all, 
        mock_release_lock, mock_acquire_lock, mock_servers_config, 
        mock_query_results, mock_db_session, mock_lock_file
    ):
        """Test main function with successful execution"""
        # Setup mocks
        mock_acquire_lock.return_value = mock_lock_file
        mock_load_servers.return_value = mock_servers_config
        mock_session_local.return_value = mock_db_session
        mock_scrape_all_servers.return_value = mock_query_results

        # Execute main function
        await main()

        # Verify execution flow
        mock_acquire_lock.assert_called_once()
        mock_create_all.assert_called_once()
        mock_load_servers.assert_called_once()
        mock_session_local.assert_called_once()
        mock_init_servers.assert_called_once_with(mock_db_session, mock_servers_config)
        mock_scrape_all_servers.assert_called_once_with(mock_servers_config)
        mock_save_results.assert_called_once_with(mock_db_session, mock_query_results)
        mock_db_session.close.assert_called_once()
        mock_release_lock.assert_called_once_with(mock_lock_file)

    @patch('scraper.acquire_lock')
    @patch('scraper.release_lock')
    @patch('scraper.Base.metadata.create_all')
    @patch('scraper.load_servers')
    @patch('scraper.SessionLocal')
    @pytest.mark.asyncio
    async def test_main_with_load_servers_exception(
        self, mock_session_local, mock_load_servers, mock_create_all,
        mock_release_lock, mock_acquire_lock, mock_lock_file
    ):
        """Test main function when load_servers raises an exception"""
        # Setup mocks
        mock_acquire_lock.return_value = mock_lock_file
        mock_load_servers.side_effect = FileNotFoundError("servers.json not found")

        # Execute and verify exception handling
        with pytest.raises(FileNotFoundError):
            await main()

        # Verify cleanup is still called
        mock_acquire_lock.assert_called_once()
        mock_release_lock.assert_called_once_with(mock_lock_file)

    @patch('scraper.acquire_lock')
    @patch('scraper.release_lock') 
    @patch('scraper.Base.metadata.create_all')
    @patch('scraper.load_servers')
    @patch('scraper.SessionLocal')
    @patch('scraper.init_servers')
    @patch('scraper.scrape_all_servers')
    @pytest.mark.asyncio
    async def test_main_with_database_exception(
        self, mock_scrape_all_servers, mock_init_servers, mock_session_local,
        mock_load_servers, mock_create_all, mock_release_lock, mock_acquire_lock,
        mock_servers_config, mock_db_session, mock_lock_file
    ):
        """Test main function when database operations fail"""
        # Setup mocks
        mock_acquire_lock.return_value = mock_lock_file
        mock_load_servers.return_value = mock_servers_config
        mock_session_local.return_value = mock_db_session
        mock_init_servers.side_effect = Exception("Database connection failed")

        # Execute and verify exception handling
        with pytest.raises(Exception):
            await main()

        # Verify database session is still closed
        mock_db_session.close.assert_called_once()
        mock_release_lock.assert_called_once_with(mock_lock_file)

    @patch('builtins.open', new_callable=mock_open)
    @patch('fcntl.lockf')
    def test_acquire_lock_success(self, mock_lockf, mock_file):
        """Test successful lock acquisition"""
        mock_lockf.return_value = None  # Successful lock
        
        result = acquire_lock()
        
        mock_file.assert_called_once_with("/tmp/minecraft_scraper.lock", "w")
        mock_lockf.assert_called_once()
        assert result == mock_file.return_value

    @patch('builtins.open', new_callable=mock_open)
    @patch('fcntl.lockf')
    @patch('sys.exit')
    def test_acquire_lock_already_locked(self, mock_exit, mock_lockf, mock_file):
        """Test lock acquisition when already locked"""
        mock_lockf.side_effect = IOError("Lock failed")
        
        acquire_lock()
        
        mock_exit.assert_called_once_with(1)

    @patch('fcntl.lockf')
    @patch('os.remove')
    def test_release_lock_success(self, mock_remove, mock_lockf):
        """Test successful lock release"""
        mock_lock_file = Mock()
        
        release_lock(mock_lock_file)
        
        mock_lockf.assert_called_once_with(mock_lock_file, fcntl.LOCK_UN)
        mock_lock_file.close.assert_called_once()
        mock_remove.assert_called_once_with("/tmp/minecraft_scraper.lock")

    @patch('fcntl.lockf')
    @patch('os.remove')
    def test_release_lock_with_remove_exception(self, mock_remove, mock_lockf):
        """Test lock release when file removal fails"""
        mock_lock_file = Mock()
        mock_remove.side_effect = OSError("Permission denied")
        
        # Should not raise exception
        release_lock(mock_lock_file)
        
        mock_lockf.assert_called_once()
        mock_lock_file.close.assert_called_once()

    @patch('builtins.open', new_callable=mock_open, read_data='[{"id": "test", "name": "Test", "ip": "test.com", "port": 25565}]')
    @patch('json.load')
    def test_load_servers_success(self, mock_json_load, mock_file):
        """Test successful server configuration loading"""
        expected_config = [{"id": "test", "name": "Test", "ip": "test.com", "port": 25565}]
        mock_json_load.return_value = expected_config
        
        result = load_servers()
        
        mock_file.assert_called_once_with('servers.json', 'r')
        assert result == expected_config

    def test_init_servers_new_server(self, mock_servers_config, mock_db_session):
        """Test initializing new servers in database"""
        # Mock that no servers exist
        mock_db_session.query.return_value.filter.return_value.first.return_value = None
        
        init_servers(mock_db_session, mock_servers_config)
        
        # Should add both servers
        assert mock_db_session.add.call_count == 2
        mock_db_session.commit.assert_called_once()

    def test_init_servers_existing_server(self, mock_servers_config, mock_db_session):
        """Test initializing when servers already exist"""
        # Mock that servers already exist
        mock_server = Mock()
        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_server
        
        init_servers(mock_db_session, mock_servers_config)
        
        # Should not add any servers
        mock_db_session.add.assert_not_called()
        mock_db_session.commit.assert_called_once()

    @patch('scraper.JavaServer')
    @pytest.mark.asyncio
    async def test_query_server_success(self, mock_java_server):
        """Test successful server query"""
        # Setup mocks - create player objects with name attribute
        player1 = Mock()
        player1.name = "player1"
        player2 = Mock()
        player2.name = "player2"
        player3 = Mock()
        player3.name = "player3"
        
        mock_status = Mock()
        mock_status.players.online = 3
        mock_status.players.sample = [player1, player2, player3]
        
        mock_server_instance = Mock()
        mock_server_instance.async_status = AsyncMock(return_value=mock_status)
        mock_java_server.return_value = mock_server_instance
        
        server_config = {
            "id": "test",
            "name": "Test Server",
            "ip": "test.com",
            "port": 25565
        }
        
        result = await query_server(server_config)
        
        expected = {
            "server_id": "test",
            "player_count": 3,
            "players": ["player1", "player2", "player3"],
            "success": True
        }
        
        assert result == expected
        mock_java_server.assert_called_once_with("test.com", 25565)

    @patch('scraper.JavaServer')
    @pytest.mark.asyncio
    async def test_query_server_no_players(self, mock_java_server):
        """Test server query with no players online"""
        # Setup mocks
        mock_status = Mock()
        mock_status.players.online = 0
        mock_status.players.sample = None
        
        mock_server_instance = Mock()
        mock_server_instance.async_status = AsyncMock(return_value=mock_status)
        mock_java_server.return_value = mock_server_instance
        
        server_config = {
            "id": "test",
            "name": "Test Server", 
            "ip": "test.com",
            "port": 25565
        }
        
        result = await query_server(server_config)
        
        expected = {
            "server_id": "test",
            "player_count": 0,
            "players": [],
            "success": True
        }
        
        assert result == expected

    @patch('scraper.JavaServer')
    @pytest.mark.asyncio
    async def test_query_server_exception(self, mock_java_server):
        """Test server query with exception"""
        mock_java_server.side_effect = Exception("Connection timeout")
        
        server_config = {
            "id": "test",
            "name": "Test Server",
            "ip": "test.com", 
            "port": 25565
        }
        
        result = await query_server(server_config)
        
        expected = {
            "server_id": "test",
            "player_count": 0,
            "players": [],
            "success": False
        }
        
        assert result == expected

    @patch('scraper.query_server')
    @pytest.mark.asyncio
    async def test_scrape_all_servers(self, mock_query_server, mock_servers_config, mock_query_results):
        """Test scraping all servers concurrently"""
        mock_query_server.side_effect = mock_query_results
        
        result = await scrape_all_servers(mock_servers_config)
        
        assert result == mock_query_results
        assert mock_query_server.call_count == 2

    @patch('scraper.datetime')
    def test_save_results_success(self, mock_datetime, mock_query_results, mock_db_session):
        """Test successful saving of scraping results"""
        # Setup mocks
        mock_timestamp = datetime(2024, 1, 1, 12, 0, 0)
        mock_datetime.utcnow.return_value = mock_timestamp
        
        # Mock player queries to return None (new players)
        mock_db_session.query.return_value.filter.return_value.first.return_value = None
        
        # Create mock PlayerCount objects with players relationship
        mock_player_count1 = Mock()
        mock_player_count1.players = Mock()
        mock_player_count1.players.append = Mock()
        
        mock_player_count2 = Mock()
        mock_player_count2.players = Mock()
        mock_player_count2.players.append = Mock()
        
        # Mock PlayerCount constructor to return our mocks
        with patch('scraper.PlayerCount', side_effect=[mock_player_count1, mock_player_count2]):
            with patch('scraper.Player') as mock_player_class:
                # Mock Player instances
                mock_player_instances = [Mock() for _ in range(5)]  # 5 players total
                mock_player_class.side_effect = mock_player_instances
                
                save_results(mock_db_session, mock_query_results)
        
        # Should create PlayerCount entries for successful results (2) + players (5)
        assert mock_db_session.add.call_count == 7  # 2 PlayerCount + 5 players
        assert mock_db_session.flush.call_count >= 2
        mock_db_session.commit.assert_called_once()

    @patch('scraper.datetime')
    def test_save_results_with_failed_query(self, mock_datetime, mock_db_session):
        """Test saving results when some queries failed"""
        mock_timestamp = datetime(2024, 1, 1, 12, 0, 0)
        mock_datetime.utcnow.return_value = mock_timestamp
        
        results_with_failure = [
            {
                "server_id": "test1",
                "player_count": 5,
                "players": ["player1"],
                "success": True
            },
            {
                "server_id": "test2", 
                "player_count": 0,
                "players": [],
                "success": False  # Failed query
            }
        ]
        
        mock_db_session.query.return_value.filter.return_value.first.return_value = None
        
        # Create mock PlayerCount with players relationship
        mock_player_count = Mock()
        mock_player_count.players = Mock()
        mock_player_count.players.append = Mock()
        
        with patch('scraper.PlayerCount', return_value=mock_player_count):
            with patch('scraper.Player') as mock_player_class:
                mock_player_class.return_value = Mock()
                
                save_results(mock_db_session, results_with_failure)
        
        # Should only process successful results
        # 1 PlayerCount + 1 Player = 2 adds
        assert mock_db_session.add.call_count == 2
        mock_db_session.commit.assert_called_once()

    @patch('scraper.datetime')
    def test_save_results_existing_players(self, mock_datetime, mock_db_session):
        """Test saving results with existing players"""
        mock_timestamp = datetime(2024, 1, 1, 12, 0, 0)
        mock_datetime.utcnow.return_value = mock_timestamp
        
        # Mock existing player
        mock_existing_player = Mock()
        
        # Create a mock PlayerCount with an append method for players relationship
        mock_player_count = Mock()
        mock_player_count.players = Mock()
        mock_player_count.players.append = Mock()
        
        # Set up the query chain to return existing player
        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_existing_player
        
        # Mock the PlayerCount constructor to return our mock
        with patch('scraper.PlayerCount', return_value=mock_player_count):
            results = [
                {
                    "server_id": "test1",
                    "player_count": 1,
                    "players": ["existing_player"],
                    "success": True
                }
            ]
            
            save_results(mock_db_session, results)
        
        # Should create PlayerCount but not new Player
        assert mock_db_session.add.call_count == 1  # Only PlayerCount
        mock_db_session.commit.assert_called_once()
        mock_player_count.players.append.assert_called_once_with(mock_existing_player)

    @pytest.mark.integration
    @patch('scraper.acquire_lock')
    @patch('scraper.release_lock')
    @patch('scraper.Base.metadata.create_all')
    @patch('scraper.load_servers')
    @patch('scraper.SessionLocal')
    @patch('scraper.query_server')
    @pytest.mark.asyncio
    async def test_main_integration(
        self, mock_query_server, mock_session_local, mock_load_servers,
        mock_create_all, mock_release_lock, mock_acquire_lock,
        mock_servers_config, mock_db_session, mock_lock_file
    ):
        """Integration test for main function with real flow"""
        # Setup all mocks for a complete flow
        mock_acquire_lock.return_value = mock_lock_file
        mock_load_servers.return_value = mock_servers_config
        mock_session_local.return_value = mock_db_session
        
        # Mock successful queries
        mock_query_server.side_effect = [
            {
                "server_id": "test1",
                "player_count": 3,
                "players": ["player1", "player2", "player3"],
                "success": True
            },
            {
                "server_id": "test2",
                "player_count": 0, 
                "players": [],
                "success": True
            }
        ]
        
        # Mock database operations
        mock_db_session.query.return_value.filter.return_value.first.return_value = None
        
        await main()
        
        # Verify complete execution
        mock_acquire_lock.assert_called_once()
        mock_load_servers.assert_called_once()
        assert mock_query_server.call_count == 2
        mock_db_session.commit.assert_called()
        mock_db_session.close.assert_called_once()
        mock_release_lock.assert_called_once_with(mock_lock_file)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])