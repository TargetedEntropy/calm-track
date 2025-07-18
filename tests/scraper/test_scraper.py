"""
Simplified tests for scraper.py - focusing on the most important functionality.
"""

import pytest
import asyncio
import json
import tempfile
import os
from unittest.mock import Mock, patch, AsyncMock, mock_open
from datetime import datetime
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from scraper import load_servers, query_server, scrape_all_servers
from models.models import Server, PlayerCount, Player


class TestLoadServers:
    """Test server configuration loading"""

    def test_load_servers_valid_json(self):
        """Test loading valid servers.json"""
        servers_data = [
            {"id": "test1", "name": "Test Server 1", "ip": "127.0.0.1", "port": 25565},
            {
                "id": "test2",
                "name": "Test Server 2",
                "ip": "example.com",
                "port": 25566,
            },
        ]

        with patch("builtins.open", mock_open(read_data=json.dumps(servers_data))):
            result = load_servers()
            assert result == servers_data
            assert len(result) == 2
            assert result[0]["id"] == "test1"

    def test_load_servers_file_not_found(self):
        """Test behavior when servers.json doesn't exist"""
        with patch("builtins.open", side_effect=FileNotFoundError("No such file")):
            with pytest.raises(FileNotFoundError):
                load_servers()

    def test_load_servers_invalid_json(self):
        """Test behavior with malformed JSON"""
        with patch("builtins.open", mock_open(read_data="{ invalid json")):
            with pytest.raises(json.JSONDecodeError):
                load_servers()


class TestQueryServer:
    """Test individual server querying"""

    @pytest.fixture
    def server_config(self):
        return {
            "id": "test_server",
            "name": "Test Server",
            "ip": "127.0.0.1",
            "port": 25565,
        }

    @pytest.mark.asyncio
    async def test_query_server_success_with_players(self, server_config):
        """Test successful query with online players"""
        # Create mock player objects
        mock_player1 = Mock()
        mock_player1.name = "Player1"
        mock_player2 = Mock()
        mock_player2.name = "Player2"

        # Create mock status
        mock_status = Mock()
        mock_status.players.online = 2
        mock_status.players.sample = [mock_player1, mock_player2]

        # Create mock server
        mock_server = AsyncMock()
        mock_server.async_status.return_value = mock_status

        with patch("scraper.JavaServer", return_value=mock_server):
            result = await query_server(server_config)

            assert result["success"] is True
            assert result["server_id"] == "test_server"
            assert result["player_count"] == 2
            assert result["players"] == ["Player1", "Player2"]

    @pytest.mark.asyncio
    async def test_query_server_success_empty(self, server_config):
        """Test successful query with no players"""
        mock_status = Mock()
        mock_status.players.online = 0
        mock_status.players.sample = None

        mock_server = AsyncMock()
        mock_server.async_status.return_value = mock_status

        with patch("scraper.JavaServer", return_value=mock_server):
            result = await query_server(server_config)

            assert result["success"] is True
            assert result["server_id"] == "test_server"
            assert result["player_count"] == 0
            assert result["players"] == []

    @pytest.mark.asyncio
    async def test_query_server_connection_error(self, server_config):
        """Test query with connection error"""
        mock_server = AsyncMock()
        mock_server.async_status.side_effect = ConnectionError("Connection refused")

        with patch("scraper.JavaServer", return_value=mock_server):
            result = await query_server(server_config)

            assert result["success"] is False
            assert result["server_id"] == "test_server"
            assert result["player_count"] == 0
            assert result["players"] == []

    @pytest.mark.asyncio
    async def test_query_server_filters_empty_names(self, server_config):
        """Test that empty player names are filtered out"""
        mock_player1 = Mock()
        mock_player1.name = "ValidPlayer"
        mock_player2 = Mock()
        mock_player2.name = ""  # Empty name
        mock_player3 = Mock()
        mock_player3.name = None  # None name

        mock_status = Mock()
        mock_status.players.online = 1
        mock_status.players.sample = [mock_player1, mock_player2, mock_player3]

        mock_server = AsyncMock()
        mock_server.async_status.return_value = mock_status

        with patch("scraper.JavaServer", return_value=mock_server):
            result = await query_server(server_config)

            assert result["success"] is True
            assert result["players"] == ["ValidPlayer"]


class TestScrapeAllServers:
    """Test concurrent server scraping"""

    @pytest.mark.asyncio
    async def test_scrape_all_servers_multiple(self):
        """Test scraping multiple servers concurrently"""
        servers_config = [
            {"id": "server1", "name": "Server 1", "ip": "127.0.0.1", "port": 25565},
            {"id": "server2", "name": "Server 2", "ip": "127.0.0.1", "port": 25566},
        ]

        expected_results = [
            {
                "server_id": "server1",
                "player_count": 3,
                "players": ["Player1"],
                "success": True,
            },
            {
                "server_id": "server2",
                "player_count": 1,
                "players": ["Player2"],
                "success": True,
            },
        ]

        with patch("scraper.query_server", side_effect=expected_results):
            results = await scrape_all_servers(servers_config)

            assert len(results) == 2
            assert results == expected_results

    @pytest.mark.asyncio
    async def test_scrape_all_servers_empty_list(self):
        """Test scraping with empty server list"""
        results = await scrape_all_servers([])
        assert results == []

    @pytest.mark.asyncio
    async def test_scrape_all_servers_mixed_results(self):
        """Test scraping with some failures"""
        servers_config = [
            {"id": "server1", "name": "Server 1", "ip": "127.0.0.1", "port": 25565},
            {"id": "server2", "name": "Server 2", "ip": "127.0.0.1", "port": 25566},
        ]

        expected_results = [
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
            },
        ]

        with patch("scraper.query_server", side_effect=expected_results):
            results = await scrape_all_servers(servers_config)

            assert len(results) == 2
            assert results[0]["success"] is True
            assert results[1]["success"] is False


class TestFileOperations:
    """Test file operations and edge cases"""

    def test_load_servers_with_extra_fields(self):
        """Test loading servers.json with extra fields"""
        servers_data = [
            {
                "id": "test1",
                "name": "Test Server 1",
                "ip": "127.0.0.1",
                "port": 25565,
                "extra_field": "should_be_ignored",
                "description": "A test server",
            }
        ]

        with patch("builtins.open", mock_open(read_data=json.dumps(servers_data))):
            result = load_servers()
            assert len(result) == 1
            assert result[0]["id"] == "test1"
            assert "extra_field" in result[0]  # Extra fields preserved

    def test_load_servers_minimal_fields(self):
        """Test loading servers.json with only required fields"""
        servers_data = [
            {"id": "test1", "name": "Test Server 1", "ip": "127.0.0.1", "port": 25565}
        ]

        with patch("builtins.open", mock_open(read_data=json.dumps(servers_data))):
            result = load_servers()
            assert len(result) == 1
            assert all(key in result[0] for key in ["id", "name", "ip", "port"])


class TestErrorHandling:
    """Test error handling scenarios"""

    @pytest.mark.asyncio
    async def test_query_server_timeout(self):
        """Test query server with timeout"""
        server_config = {"id": "test", "name": "Test", "ip": "127.0.0.1", "port": 25565}

        mock_server = AsyncMock()
        mock_server.async_status.side_effect = asyncio.TimeoutError("Timeout")

        with patch("scraper.JavaServer", return_value=mock_server):
            result = await query_server(server_config)

            assert result["success"] is False
            assert result["server_id"] == "test"

    @pytest.mark.asyncio
    async def test_query_server_generic_exception(self):
        """Test query server with generic exception"""
        server_config = {"id": "test", "name": "Test", "ip": "127.0.0.1", "port": 25565}

        mock_server = AsyncMock()
        mock_server.async_status.side_effect = Exception("Unknown error")

        with patch("scraper.JavaServer", return_value=mock_server):
            result = await query_server(server_config)

            assert result["success"] is False
            assert result["player_count"] == 0
            assert result["players"] == []


# Simple test runner
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
