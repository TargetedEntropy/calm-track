from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Table
from sqlalchemy.orm import relationship

from .database import Base

player_snapshot_association = Table(
    "player_snapshot_association",
    Base.metadata,
    Column("player_count_id", Integer, ForeignKey("player_counts.id")),
    Column("player_id", Integer, ForeignKey("players.id")),
)


class Server(Base):
    __tablename__ = "servers"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    ip = Column(String, nullable=False)
    port = Column(Integer, nullable=False)

    player_counts = relationship("PlayerCount", back_populates="server")


class PlayerCount(Base):
    __tablename__ = "player_counts"

    id = Column(Integer, primary_key=True, index=True)
    server_id = Column(String, ForeignKey("servers.id"))
    timestamp = Column(DateTime, default=datetime.utcnow)
    player_count = Column(Integer, nullable=False)

    server = relationship("Server", back_populates="player_counts")
    players = relationship(
        "Player", secondary=player_snapshot_association, back_populates="snapshots"
    )


class Player(Base):
    __tablename__ = "players"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)

    snapshots = relationship(
        "PlayerCount", secondary=player_snapshot_association, back_populates="players"
    )
