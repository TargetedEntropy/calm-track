from fastapi import FastAPI, Query, HTTPException, Depends
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import func
from sqlalchemy.orm import Session
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
def get_servers(db: Session = Depends(get_db)):  # Use dependency injection
    """Get list of all monitored servers"""
    servers = db.query(Server).all()
    return [{"id": s.id, "name": s.name, "ip": s.ip, "port": s.port} for s in servers]


@app.get("/graph/{server_id}")
async def generate_graph(
    server_id: str,
    period: int = Query(default=7, ge=1, le=365, description="Number of days to display"),
    db: Session = Depends(get_db)  
):
    """Generate a line graph of player counts for a specific server"""
    
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
    
    # Save to BytesIO buffer instead of file
    buffer = BytesIO()
    plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
    plt.close()
    buffer.seek(0)
    
    # Convert to base64 for embedding in HTML
    image_base64 = base64.b64encode(buffer.getvalue()).decode()
    
    # Create HTML page to display the graph
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{server.name} - Player Count</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 20px;
                background-color: #f5f5f5;
                display: flex;
                flex-direction: column;
                align-items: center;
            }}
            .container {{
                background-color: white;
                padding: 20px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                max-width: 1200px;
                width: 100%;
            }}
            img {{
                width: 100%;
                height: auto;
                border-radius: 4px;
            }}
            .controls {{
                margin: 20px 0;
                text-align: center;
            }}
            .controls a {{
                margin: 0 10px;
                padding: 8px 16px;
                background-color: #007bff;
                color: white;
                text-decoration: none;
                border-radius: 4px;
                display: inline-block;
            }}
            .controls a:hover {{
                background-color: #0056b3;
            }}
            .info {{
                text-align: center;
                color: #666;
                margin-top: 10px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1 style="text-align: center; color: #333;">{server.name} - Player Count</h1>
            <div class="controls">
                <a href="/graph/{server_id}?period=1">1 Day</a>
                <a href="/graph/{server_id}?period=7">7 Days</a>
                <a href="/graph/{server_id}?period=30">30 Days</a>
                <a href="/graph/{server_id}?period=90">90 Days</a>
                <a href="/graph/{server_id}?period=365">1 Year</a>
            </div>
            <img src="data:image/png;base64,{image_base64}" alt="Player Count Graph">
            <div class="info">
                <p>Server: {server.name} ({server.ip}:{server.port})</p>
                <p>Period: {period} days | Data points: {len(player_counts)}</p>
                <p>Last updated: {end_date.strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)
        
@app.get("/graph/{server_id}/image")
async def get_graph_image(
    server_id: str,
    period: int = Query(default=7, ge=1, le=365, description="Number of days to display"),
    db: Session = Depends(get_db)
):
    """Get just the graph image as PNG (for embedding in other pages)"""

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
    
    # Save to BytesIO buffer
    buffer = BytesIO()
    plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
    plt.close()
    buffer.seek(0)
    
    # Return as PNG response
    return Response(content=buffer.getvalue(), media_type="image/png")


@app.get("/stats/{server_id}")
def get_server_stats(
    server_id: str,
    period: int = Query(default=7, ge=1, le=365, description="Number of days for statistics"),
    db: Session = Depends(get_db) 
):
    """Get statistics for a specific server"""

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
    


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=23282)