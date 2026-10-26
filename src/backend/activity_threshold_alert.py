#!/usr/bin/env python3
"""
Activity Threshold Alert System

This script monitors activities in the zone_activities table and raises alerts
when activities exceed their thresholds as defined in the client_activities table.

Usage:
    python activity_threshold_alert.py [--check-period MINUTES]

Options:
    --check-period MINUTES    How far back to check activities (default: 60 minutes)
"""

import os
import sys
import logging
import argparse
import json
from datetime import datetime, timedelta
from typing import Dict, List, Set, Tuple
from collections import defaultdict

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("activity_threshold_alerts.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Import database functions
from sqlalchemy import create_engine, func, and_, between, or_, text
from sqlalchemy.orm import sessionmaker, joinedload
from sqlalchemy.ext.declarative import declarative_base
from database import (
    get_session as get_main_session, get_client_activities, ClientActivity, 
    ZoneActivity, Notification, Zone, Camera
)

# Database configuration
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_HOST = os.getenv('DB_HOST')
DB_PORT = os.getenv('DB_PORT')

# Validate database configuration
if not all([DB_USER, DB_PASSWORD, DB_HOST, DB_PORT]):
    raise ValueError("Database configuration is incomplete. Please check your environment variables.")

logger.info(f"Using database configuration - Host: {DB_HOST}, Port: {DB_PORT}, User: {DB_USER}")


def get_client_database_session(client_uuid: str):
    """Create a session for a specific client database."""
    try:
        db_name = f"hawkeye_client_{client_uuid}"
        connection_string = f'postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{db_name}'
        engine = create_engine(connection_string)
        Session = sessionmaker(bind=engine)
        return Session()
    except Exception as e:
        logger.error(f"Error creating database session for client {client_uuid}: {str(e)}")
        raise

def get_all_clients():
    """Get all clients from the hawkeye_clients database."""
    try:
        connection_string = f'postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/hawkeye_clients'
        logger.info(f"Connecting to hawkeye_clients database at {DB_HOST}:{DB_PORT}")
        engine = create_engine(connection_string)
        Session = sessionmaker(bind=engine)
        session = Session()
        try:
            # Query the clients table
            result = session.execute(text('SELECT client_uuid FROM clients'))
            clients = [row[0] for row in result]
            if not clients:
                logger.warning("No clients found in hawkeye_clients database")
            else:
                logger.info(f"Found {len(clients)} clients in database")
            return clients
        except Exception as e:
            logger.error(f"Error querying clients: {str(e)}")
            return []
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Error connecting to hawkeye_clients database: {str(e)}")
        return []

def add_notification(header: str, description: str, severity: str, client_uuid: str) -> Notification:
    """Add a new notification to the client's database.
    
    Args:
        header: The notification header
        description: The notification description
        severity: The notification severity (HIGH, MED, LOW)
        client_uuid: The client's UUID
        
    Returns:
        The newly created notification
    """
    session = get_client_database_session(client_uuid)
    try:
        # Validate severity
        if severity not in ['HIGH', 'MED', 'LOW']:
            logger.warning(f"Invalid severity: {severity}. Using 'MED' instead.")
            severity = 'MED'
            
        notification = Notification(
            header=header,
            description=description,
            severity=severity
        )
        session.add(notification)
        session.commit()
        session.refresh(notification)
        logger.info(f"Created notification for client {client_uuid}: {notification.header}")
        return notification
    except Exception as e:
        session.rollback()
        logger.error(f"Error adding notification for client {client_uuid}: {str(e)}")
        raise
    finally:
        session.close()

def get_activity_durations(start_time: datetime, end_time: datetime, client_uuid: str) -> Dict[str, Dict[Tuple[str, int], float]]:
    """
    Calculate the duration of activities in minutes for a specific client.
    
    Args:
        start_time: The start time to filter activities
        end_time: The end time to filter activities
        client_uuid: The client's UUID
        
    Returns:
        Dictionary with activity types as keys and dictionaries of (zone_uuid, track_id) -> duration in minutes as values
    """
    logger.info(f"Calculating activity durations for client {client_uuid} from {start_time} to {end_time}")
    
    session = get_client_database_session(client_uuid)
    try:
        # Query for all activities between start_time and end_time
        activities = session.query(
            ZoneActivity.activity_type,
            ZoneActivity.zone_uuid,
            ZoneActivity.zone_track_id,
            ZoneActivity.timestamp,
            Zone.name.label('zone_name'),
            Camera.name.label('camera_name')
        ).join(Zone, ZoneActivity.zone_uuid == Zone.zone_uuid
        ).join(Camera, ZoneActivity.camera_uuid == Camera.camera_uuid
        ).filter(
            ZoneActivity.timestamp.between(start_time, end_time),
            ZoneActivity.is_primary == True  # Only consider primary activities
        ).order_by(
            ZoneActivity.activity_type,
            ZoneActivity.zone_uuid,
            ZoneActivity.zone_track_id,
            ZoneActivity.timestamp
        ).all()
        
        if not activities:
            logger.info(f"No activities found for client {client_uuid} in the specified time range")
            return {}
            
        # Group by activity_type, zone_uuid, and track_id
        activity_durations = defaultdict(dict)
        activity_metadata = {}
        
        # Group activities by type, zone, and track
        grouped_activities = defaultdict(list)
        for activity in activities:
            key = (activity.activity_type, activity.zone_uuid, activity.zone_track_id)
            grouped_activities[key].append(activity)
            if key not in activity_metadata:
                activity_metadata[key] = {
                    'zone_name': activity.zone_name,
                    'camera_name': activity.camera_name
                }
        
        # Calculate durations for each activity group
        for (activity_type, zone_uuid, track_id), activity_list in grouped_activities.items():
            activity_list.sort(key=lambda x: x.timestamp)
            
            if len(activity_list) > 1:
                first_timestamp = activity_list[0].timestamp
                last_timestamp = activity_list[-1].timestamp
                duration_minutes = (last_timestamp - first_timestamp).total_seconds() / 60
            else:
                duration_minutes = 1
            
            key = (zone_uuid, track_id)
            activity_durations[activity_type][key] = {
                'duration_minutes': duration_minutes,
                'zone_name': activity_metadata[(activity_type, zone_uuid, track_id)]['zone_name'],
                'camera_name': activity_metadata[(activity_type, zone_uuid, track_id)]['camera_name'],
                'first_seen': activity_list[0].timestamp,
                'last_seen': activity_list[-1].timestamp
            }
        
        return activity_durations
        
    except Exception as e:
        logger.error(f"Error calculating activity durations for client {client_uuid}: {str(e)}")
        raise
    finally:
        session.close()

def check_thresholds(check_period_minutes: int = 60) -> List[dict]:
    """
    Check activities against thresholds for all clients.
    
    Args:
        check_period_minutes: How far back to check activities in minutes
        
    Returns:
        List of generated alerts as dictionaries
    """
    logger.info(f"Checking activity thresholds for the past {check_period_minutes} minutes")
    
    # Calculate time range
    end_time = datetime.now()
    start_time = end_time - timedelta(minutes=check_period_minutes)
    
    # Get all clients
    clients = get_all_clients()
    if not clients:
        logger.error("No clients found in hawkeye_clients database")
        return []
        
    all_alerts = []
    
    for client_uuid in clients:
        logger.info(f"Processing client: {client_uuid}")
        session = get_client_database_session(client_uuid)
        
        try:
            # Check if client_activities table exists for this client
            try:
                session.execute(text("SELECT 1 FROM client_activities LIMIT 1"))
                table_exists = True
            except Exception as e:
                if "relation \"client_activities\" does not exist" in str(e):
                    logger.error(f"Creating client_activities table for client {client_uuid}")
                    table_exists = False
                else:
                    raise
                    
            # Create table if it doesn't exist
            if not table_exists:
                try:
                    session.execute(text("""
                        CREATE TABLE client_activities (
                            id SERIAL PRIMARY KEY,
                            activity_name VARCHAR(255) NOT NULL,
                            description TEXT,
                            threshold_minutes INTEGER DEFAULT 0,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """))
                    session.commit()
                    logger.info(f"Created client_activities table for client {client_uuid}")
                except Exception as e:
                    session.rollback()
                    logger.error(f"Error creating client_activities table for client {client_uuid}: {str(e)}")
                    continue
            
            # Get client activities with thresholds
            client_activities = session.query(ClientActivity).all()
            monitored_activities = [activity for activity in client_activities if activity.threshold_minutes > 0]
            
            if not monitored_activities:
                logger.info(f"No activities with thresholds defined for client {client_uuid}")
                continue
                
            logger.info(f"Monitoring {len(monitored_activities)} activities for client {client_uuid}")
            
            # Get activity durations for this client
            activity_durations = get_activity_durations(start_time, end_time, client_uuid)
            
            # Check each activity against its threshold
            for activity in monitored_activities:
                activity_name = activity.activity_name
                threshold_minutes = activity.threshold_minutes
                
                if activity_name not in activity_durations:
                    continue
                    
                # Check each instance of this activity
                for (zone_uuid, track_id), data in activity_durations[activity_name].items():
                    duration = data['duration_minutes']
                    if duration >= threshold_minutes:
                        alert = {
                            'client_uuid': client_uuid,
                            'activity_name': activity_name,
                            'zone_name': data['zone_name'],
                            'camera_name': data['camera_name'],
                            'duration': duration,
                            'threshold': threshold_minutes,
                            'first_seen': data['first_seen'],
                            'last_seen': data['last_seen']
                        }
                        all_alerts.append(alert)
                        logger.warning(
                            f"Alert for client {client_uuid}: {activity_name} in {data['zone_name']} "
                            f"({data['camera_name']}) exceeded threshold: {duration:.1f} minutes"
                        )
            
        except Exception as e:
            logger.error(f"Error processing client {client_uuid}: {str(e)}")
            continue
        finally:
            session.close()
    
    return all_alerts

def create_alert_notifications(alerts: List[dict]) -> None:
    """Create notifications for alerts in each client's database."""
    for alert in alerts:
        client_uuid = alert['client_uuid']
        header = f"Activity Threshold Alert: {alert['activity_name']}"
        description = (
            f"Activity '{alert['activity_name']}' in zone '{alert['zone_name']}' "
            f"({alert['camera_name']}) has been ongoing for {alert['duration']:.1f} minutes, "
            f"exceeding the threshold of {alert['threshold']} minutes.\n"
            f"First seen: {alert['first_seen']}\n"
            f"Last seen: {alert['last_seen']}"
        )
        try:
            add_notification(header, description, 'HIGH', client_uuid)
        except Exception as e:
            logger.error(f"Error creating notification for client {client_uuid}: {str(e)}")

def main():
    """Main entry point of the script."""
    parser = argparse.ArgumentParser(description="Activity Threshold Alert System")
    parser.add_argument(
        '--check-period',
        type=int,
        default=60,
        help='How far back to check activities in minutes (default: 60)'
    )
    
    args = parser.parse_args()
    
    try:
        logger.info("Starting Activity Threshold Alert System")
        logger.info(f"Check period: {args.check_period} minutes")
        
        # Check thresholds and get alerts
        alerts = check_thresholds(args.check_period)
        
        if alerts:
            # Create notifications for alerts
            create_alert_notifications(alerts)
            logger.info(f"Created {len(alerts)} alert notifications")
        else:
            logger.info("No threshold violations detected")
            
    except Exception as e:
        logger.error(f"Error in activity threshold alert system: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main() 