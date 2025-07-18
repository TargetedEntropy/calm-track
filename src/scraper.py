#!/usr/bin/env python3
import asyncio
import fcntl
import json
import os
import sys
from datetime import datetime

from dotenv import load_dotenv
from mcstatus import JavaServer
from sqlalchemy.orm import Session

from models.database import Base, SessionLocal, engine
from models.models import Player, PlayerCount, Server

load_dotenv()

LOCK_FILE = "/tmp/minecraft_scraper.lock"


def acquire_lock():
    """Prevent multiple instances from running simultaneously"""
    try:
        lock_file = open(LOCK_FILE, "w")
        fcntl.lockf(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock_file
    except IOError:
        print("Another instance is already running.")
        sys.exit(1)


def release_lock(lock_file):
    """Release the lock file"""
    fcntl.lockf(lock_file, fcntl.LOCK_UN)
    lock_file.close()
    try:
        os.remove(LOCK_FILE)
    except:
        pass


def load_servers():
    """Load server configuration from JSON file"""
    with open("servers.json", "r") as f:
        return json.load(f)


def init_servers(db: Session, servers_config):
    """Initialize servers in database if they don't exist"""
    for server_config in servers_config:
        server = db.query(Server).filter(Server.id == server_config["id"]).first()
        if not server:
            server = Server(
                id=server_config["id"],
                name=server_config["name"],
                ip=server_config["ip"],
                port=server_config["port"],
            )
            db.add(server)
    db.commit()


async def query_server(server_config):
    """Query a single Minecraft server for player information"""
    try:
        server = JavaServer(server_config["ip"], server_config["port"])
        status = await server.async_status()

        players = []
        if hasattr(status.players, "sample") and status.players.sample:
            players = [player.name for player in status.players.sample if player.name]

        return {
            "server_id": server_config["id"],
            "player_count": status.players.online,
            "players": players,
            "success": True,
        }
    except Exception as e:
        print(f"Error querying {server_config['name']}: {e}")
        return {
            "server_id": server_config["id"],
            "player_count": 0,
            "players": [],
            "success": False,
        }


async def scrape_all_servers(servers_config):
    """Scrape all servers concurrently"""
    tasks = [query_server(server) for server in servers_config]
    return await asyncio.gather(*tasks)


def save_results(db: Session, results):
    """Save scraping results to database"""
    timestamp = datetime.utcnow()

    for result in results:
        if not result["success"]:
            continue

        # Create player count entry
        player_count = PlayerCount(
            server_id=result["server_id"],
            timestamp=timestamp,
            player_count=result["player_count"],
        )
        db.add(player_count)
        db.flush()  # Get the ID

        # Handle players
        for player_name in result["players"]:
            # Get or create player
            player = db.query(Player).filter(Player.username == player_name).first()
            if not player:
                player = Player(username=player_name)
                db.add(player)
                db.flush()

            # Associate player with this snapshot
            player_count.players.append(player)

    db.commit()


async def main():
    """Main scraping function"""
    lock_file = acquire_lock()

    try:
        # Create tables if they don't exist
        Base.metadata.create_all(bind=engine)

        # Load server configuration
        servers_config = load_servers()

        # Initialize database
        db = SessionLocal()
        try:
            init_servers(db, servers_config)

            # Scrape all servers
            results = await scrape_all_servers(servers_config)

            # Save results
            save_results(db, results)

            print(f"Scraping completed at {datetime.now()}")

        finally:
            db.close()

    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    asyncio.run(main())
