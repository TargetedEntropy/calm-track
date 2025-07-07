from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import func
from datetime import datetime, timedelta
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from io import BytesIO
import base64
import os

from models.database import get_db, SessionLocal
from models.models import Server, PlayerCount

app = FastAPI(title="Minecraft Server Monitor API")

@app.get("/")
def read_root():
    return {"message": "Minecraft Server Monitor API"}

@app.get("/servers")
def get_servers():
    """Get list of all monitored servers"""
    db = SessionLocal()
    try:
        servers = db.query(Server).all()
        return [{"id": s.id, "name": s.name, "ip": s.ip, "port": s.port} for s in servers]
    finally:
        db.close()

@app.get("/graph/{server_id}")
async def generate_graph(
    server_id: str,
    period: int = Query(default=7, ge=1, le=365, description="Number of days to display")
):
    """Generate a line graph of player counts for a specific server"""
    db = SessionLocal()
    try:
        # Verify server exists
        server = db.query(Server).filter(Server.id == server_id).first()
        if not server:
            raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")
        
        # Calculate date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=period)
        
        # Query player counts
        player_counts = db.query(PlayerCount).filter(
            PlayerCount.server_id == server_id,
            PlayerCount.timestamp >= start_date,
            PlayerCount.timestamp <= end_date
        ).order_by(PlayerCount.timestamp).all()
        
        if not player_counts:
            raise HTTPException(status_code=404, detail=f"No data found for server '{server_id}' in the last {period} days")
        
        # Prepare data for plotting
        timestamps = [pc.timestamp for pc in player_counts]
        counts = [pc.player_count for pc in player_counts]
        
        # Create the plot
        plt.figure(figsize=(12, 6))
        plt.plot(timestamps, counts, marker='o', linestyle='-', markersize=4)
        
        # Customize the plot
        plt.title(f"{server.name} - Player Count ({period} days)", fontsize=16)
        plt.xlabel("Date/Time", fontsize=12)
        plt.ylabel("Number of Players", fontsize=12)
        plt.grid(True, alpha=0.3)
        
        # Format x-axis
        ax = plt.gca()
        if period <= 7:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d %H:%M'))
            ax.xaxis.set_major_locator(mdates.HourLocator(interval=6))
        elif period <= 30:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
            ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
        else:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
            ax.xaxis.set_major_locator(mdates.DayLocator(interval=7))
        
        plt.xticks(rotation=45)
        plt.tight_layout()
        
        # Save to temporary file
        temp_file = f"/tmp/graph_{server_id}_{period}.png"
        plt.savefig(temp_file, dpi=150, bbox_inches='tight')
        plt.close()
        
        # Return the file
        return FileResponse(temp_file, media_type="image/png", filename=f"{server_id}_player_count_{period}d.png")
        
    finally:
        db.close()

@app.get("/stats/{server_id}")
def get_server_stats(
    server_id: str,
    period: int = Query(default=7, ge=1, le=365, description="Number of days for statistics")
):
    """Get statistics for a specific server"""
    db = SessionLocal()
    try:
        # Verify server exists
        server = db.query(Server).filter(Server.id == server_id).first()
        if not server:
            raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")
        
        # Calculate date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=period)
        
        # Query statistics
        stats = db.query(
            func.min(PlayerCount.player_count).label('min_players'),
            func.max(PlayerCount.player_count).label('max_players'),
            func.avg(PlayerCount.player_count).label('avg_players'),
            func.count(PlayerCount.id).label('total_snapshots')
        ).filter(
            PlayerCount.server_id == server_id,
            PlayerCount.timestamp >= start_date,
            PlayerCount.timestamp <= end_date
        ).first()
        
        return {
            "server_id": server_id,
            "server_name": server.name,
            "period_days": period,
            "min_players": stats.min_players or 0,
            "max_players": stats.max_players or 0,
            "avg_players": round(float(stats.avg_players or 0), 2),
            "total_snapshots": stats.total_snapshots or 0
        }
        
    finally:
        db.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)