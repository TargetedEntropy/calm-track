from datetime import datetime, timedelta

import matplotlib
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

matplotlib.use("Agg")
import base64
import os
from io import BytesIO
from typing import List, Tuple

import matplotlib.dates as mdates
import matplotlib.pyplot as plt

from models.database import SessionLocal, get_db
from models.models import PlayerCount, Server

app = FastAPI(title="Minecraft Server Monitor API")
templates = Jinja2Templates(directory="templates")


def get_server_by_id(server_id: str, db: Session) -> Server:
    """Get server by ID or raise 404"""
    server = db.query(Server).filter(Server.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")
    return server


def get_player_counts(server_id: str, period: int, db: Session) -> List[PlayerCount]:
    """Get player counts for a server within the specified period"""
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=period)

    player_counts = (
        db.query(PlayerCount)
        .filter(
            PlayerCount.server_id == server_id,
            PlayerCount.timestamp >= start_date,
            PlayerCount.timestamp <= end_date,
        )
        .order_by(PlayerCount.timestamp)
        .all()
    )

    if not player_counts:
        raise HTTPException(
            status_code=404,
            detail=f"No data found for server '{server_id}' in the last {period} days",
        )

    return player_counts


def format_x_axis(ax, period: int):
    """Format x-axis based on the time period"""
    if period <= 7:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d %H:%M"))
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=6))
    elif period <= 30:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
    else:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=7))


def create_plot(
    server: Server, player_counts: List[PlayerCount], period: int
) -> BytesIO:
    """Create matplotlib plot and return as BytesIO buffer"""
    timestamps = [pc.timestamp for pc in player_counts]
    counts = [pc.player_count for pc in player_counts]

    plt.figure(figsize=(12, 6))
    plt.plot(timestamps, counts, marker="o", linestyle="-", markersize=4)

    plt.title(f"{server.name} - Player Count ({period} days)", fontsize=16)
    plt.xlabel("Date/Time", fontsize=12)
    plt.ylabel("Number of Players", fontsize=12)
    plt.grid(True, alpha=0.3)

    format_x_axis(plt.gca(), period)
    plt.xticks(rotation=45)
    plt.tight_layout()

    buffer = BytesIO()
    plt.savefig(buffer, format="png", dpi=150, bbox_inches="tight")
    plt.close()
    buffer.seek(0)

    return buffer


def generate_html_content(
    server: Server,
    server_id: str,
    period: int,
    player_counts: List[PlayerCount],
    image_base64: str,
) -> str:
    """Generate HTML content for the graph page using Jinja2 template"""
    end_date = datetime.utcnow()

    context = {
        "server": server,
        "server_id": server_id,
        "period": period,
        "data_points": len(player_counts),
        "last_updated": end_date.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "image_base64": image_base64,
    }

    return templates.get_template("graph.html").render(context)


@app.get("/")
def read_root():
    return {"message": "Minecraft Server Monitor API"}


@app.get("/servers")
def get_servers(db: Session = Depends(get_db)):
    """Get list of all monitored servers"""
    servers = db.query(Server).all()
    return [{"id": s.id, "name": s.name, "ip": s.ip, "port": s.port} for s in servers]


@app.get("/graph/{server_id}")
async def generate_graph(
    server_id: str,
    period: int = Query(
        default=7, ge=1, le=365, description="Number of days to display"
    ),
    db: Session = Depends(get_db),
):
    """Generate a line graph of player counts for a specific server"""
    server = get_server_by_id(server_id, db)
    player_counts = get_player_counts(server_id, period, db)

    buffer = create_plot(server, player_counts, period)
    image_base64 = base64.b64encode(buffer.getvalue()).decode()

    html_content = generate_html_content(
        server, server_id, period, player_counts, image_base64
    )
    return HTMLResponse(content=html_content)


@app.get("/graph/{server_id}/image")
async def get_graph_image(
    server_id: str,
    period: int = Query(
        default=7, ge=1, le=365, description="Number of days to display"
    ),
    db: Session = Depends(get_db),
):
    """Get just the graph image as PNG (for embedding in other pages)"""
    server = get_server_by_id(server_id, db)
    player_counts = get_player_counts(server_id, period, db)

    buffer = create_plot(server, player_counts, period)
    return Response(content=buffer.getvalue(), media_type="image/png")


@app.get("/stats/{server_id}")
def get_server_stats(
    server_id: str,
    period: int = Query(
        default=7, ge=1, le=365, description="Number of days for statistics"
    ),
    db: Session = Depends(get_db),
):
    """Get statistics for a specific server"""
    server = get_server_by_id(server_id, db)

    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=period)

    stats = (
        db.query(
            func.min(PlayerCount.player_count).label("min_players"),
            func.max(PlayerCount.player_count).label("max_players"),
            func.avg(PlayerCount.player_count).label("avg_players"),
            func.count(PlayerCount.id).label("total_snapshots"),
        )
        .filter(
            PlayerCount.server_id == server_id,
            PlayerCount.timestamp >= start_date,
            PlayerCount.timestamp <= end_date,
        )
        .first()
    )

    return {
        "server_id": server_id,
        "server_name": server.name,
        "period_days": period,
        "min_players": stats.min_players or 0,
        "max_players": stats.max_players or 0,
        "avg_players": round(float(stats.avg_players or 0), 2),
        "total_snapshots": stats.total_snapshots or 0,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=23282)
