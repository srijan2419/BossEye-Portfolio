import numpy as np
import cv2
from pathlib import Path
import logging
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime
import os
from dotenv import load_dotenv
import json
from scipy.optimize import linear_sum_assignment

# Load environment variables
load_dotenv()
DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'

# Set up logging with different levels based on DEBUG flag
logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.FileHandler('tracker_debug.log') if DEBUG else logging.FileHandler('tracker.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class AdvancedKalmanFilter:
    """Enhanced Kalman filter for tracking with better motion modeling"""
    def __init__(self):
        # State: [x, y, vx, vy, ax, ay] - position, velocity, acceleration
        self.state = np.zeros(6)
        self.prediction = np.zeros(6)
        
        # Process noise - lower for smoother tracking, higher for more responsive
        self.process_noise = np.diag([0.01, 0.01, 0.1, 0.1, 0.2, 0.2])
        
        # Measurement noise - how much we trust measurements
        self.measurement_noise = np.diag([0.1, 0.1])
        
        # State transition matrix - how state evolves over time (physics model)
        self.F = np.array([
            [1, 0, 1, 0, 0.5, 0],     # x += vx + 0.5*ax
            [0, 1, 0, 1, 0, 0.5],     # y += vy + 0.5*ay
            [0, 0, 1, 0, 1, 0],       # vx += ax
            [0, 0, 0, 1, 0, 1],       # vy += ay
            [0, 0, 0, 0, 1, 0],       # ax stays the same
            [0, 0, 0, 0, 0, 1]        # ay stays the same
        ])
        
        # Covariance matrix - uncertainty in our state estimate
        self.P = np.eye(6) * 10
        
        self.initialized = False
        self.age = 0
        self.hits = 0
        self.hit_streak = 0
        self.time_since_update = 0
        
        if DEBUG:
            logger.debug("Initialized enhanced Kalman filter")
    
    def init(self, x: float, y: float, vx: float = 0, vy: float = 0):
        """Initialize the filter with a position and optional velocity"""
        self.state = np.array([x, y, vx, vy, 0, 0])
        self.initialized = True
        self.age = 0
        self.hits = 1
        self.hit_streak = 1
        self.time_since_update = 0
        
        if DEBUG:
            logger.debug(f"Initialized Kalman state with position ({x}, {y}), velocity ({vx}, {vy})")
    
    def predict(self) -> np.ndarray:
        """Predict next position using physics model"""
        if not self.initialized:
            return np.zeros(2)
        
        # Age the track
        self.age += 1
        self.time_since_update += 1
        
        # Basic Kalman prediction
        self.state = self.F @ self.state
        self.P = self.F @ self.P @ self.F.T + self.process_noise
        
        # Update prediction
        self.prediction = self.state.copy()
        
        if DEBUG and self.time_since_update < 5:
            logger.debug(f"Predicted position: ({self.prediction[0]:.2f}, {self.prediction[1]:.2f}), " +
                         f"velocity: ({self.prediction[2]:.2f}, {self.prediction[3]:.2f})")
        
        return self.prediction[:2]
    
    def update(self, x: float, y: float):
        """Update the filter with a new measurement"""
        if not self.initialized:
            self.init(x, y)
            return
        
        # Measurement matrix - how we observe the state
        H = np.array([
            [1, 0, 0, 0, 0, 0],  # We observe x directly
            [0, 1, 0, 0, 0, 0]   # We observe y directly
        ])
        
        # Measurement
        z = np.array([x, y])
        
        # Innovation (measurement - prediction)
        y = z - H @ self.state
        
        # Innovation covariance
        S = H @ self.P @ H.T + self.measurement_noise
        
        # Kalman gain
        K = self.P @ H.T @ np.linalg.inv(S)
        
        # Update state and covariance
        self.state = self.state + K @ y
        self.P = (np.eye(6) - K @ H) @ self.P
        
        # Update tracking metrics
        self.hits += 1
        self.hit_streak += 1
        self.time_since_update = 0
        
        if DEBUG:
            logger.debug(f"Updated state - Position: ({self.state[0]:.2f}, {self.state[1]:.2f}), " +
                         f"Velocity: ({self.state[2]:.2f}, {self.state[3]:.2f})")

    def get_state(self) -> np.ndarray:
        """Get current state"""
        return self.state
    
    def get_track_quality(self) -> float:
        """Return a quality metric for the track between 0-1"""
        # Quality is higher for tracks that:
        # 1. Have been tracked for longer (higher hit_streak)
        # 2. Have been updated recently (lower time_since_update)
        # 3. Have more total hits relative to age
        
        hit_ratio = self.hits / max(1, self.age)
        recency = np.exp(-0.5 * self.time_since_update)  # Exponential decay with time since update
        streak_factor = min(1.0, self.hit_streak / 10.0)  # Cap streak factor at 1.0
        
        quality = (0.4 * hit_ratio + 0.4 * recency + 0.2 * streak_factor)
        return min(1.0, max(0.0, quality))  # Ensure between 0-1

class AppearanceModel:
    """
    Enhanced appearance model using multiple features:
    1. Color histogram (HSV)
    2. HOG features for shape
    3. Upper/lower body separation for better person re-identification
    """
    def __init__(self, frame: np.ndarray, bbox: Dict[str, float], history_size: int = 10):
        self.history_size = history_size
        self.history = []
        self.hist = None
        self.hog_features = None
        self.upper_hist = None
        self.lower_hist = None
        self.feature_weights = {
            'color': 0.4,
            'hog': 0.3,
            'upper_lower': 0.3
        }
        
        # Initialize with first frame
        if frame is not None and bbox:
            self.update(frame, bbox)
    
    def _extract_features(self, frame: np.ndarray, bbox: Dict[str, float]) -> Tuple:
        """Extract multiple appearance features from the detection"""
        # Get image dimensions
        height, width = frame.shape[:2]
        
        # Convert normalized coordinates to pixel coordinates
        x1 = max(0, int(bbox['xmin'] * width / 1000.0))
        y1 = max(0, int(bbox['ymin'] * height / 1000.0))
        x2 = min(width-1, int(bbox['xmax'] * width / 1000.0))
        y2 = min(height-1, int(bbox['ymax'] * height / 1000.0))
        
        # Check if the bounding box is valid
        if x2 <= x1 or y2 <= y1:
            # Return empty features
            empty_hist = np.zeros((16, 16, 16))
            empty_hog = np.zeros(36)
            return empty_hist, empty_hog, empty_hist, empty_hist
        
        # Extract the person region
        person_img = frame[y1:y2, x1:x2]
        if person_img.size == 0:
            # Return empty features
            empty_hist = np.zeros((16, 16, 16))
            empty_hog = np.zeros(36)
            return empty_hist, empty_hog, empty_hist, empty_hist
        
        # 1. Color histogram in HSV space
        try:
            # Resize for consistency
            resized = cv2.resize(person_img, (64, 128))
            hsv = cv2.cvtColor(resized, cv2.COLOR_BGR2HSV)
            hist = cv2.calcHist([hsv], [0, 1, 2], None, [16, 16, 16], 
                               [0, 180, 0, 256, 0, 256])
            cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
            
            # 2. HOG features for shape information
            gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
            # Simple HOG-like gradient orientation histogram
            gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0)
            gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1)
            mag, angle = cv2.cartToPolar(gx, gy)
            # Quantize angles into bins
            bins = 36
            hog_hist = np.zeros(bins)
            for i in range(bins):
                bin_mask = (angle >= (i * 2 * np.pi / bins)) & (angle < ((i + 1) * 2 * np.pi / bins))
                hog_hist[i] = np.sum(mag[bin_mask])
            if np.sum(hog_hist) > 0:
                hog_hist = hog_hist / np.sum(hog_hist)
            
            # 3. Upper/lower body separation
            h, w = resized.shape[:2]
            mid_y = h // 2
            upper_img = hsv[0:mid_y, :]
            lower_img = hsv[mid_y:, :]
            
            upper_hist = cv2.calcHist([upper_img], [0, 1], None, [16, 16], [0, 180, 0, 256])
            lower_hist = cv2.calcHist([lower_img], [0, 1], None, [16, 16], [0, 180, 0, 256])
            cv2.normalize(upper_hist, upper_hist, 0, 1, cv2.NORM_MINMAX)
            cv2.normalize(lower_hist, lower_hist, 0, 1, cv2.NORM_MINMAX)
            
            return hist, hog_hist, upper_hist, lower_hist
            
        except Exception as e:
            logger.error(f"Error extracting appearance features: {e}")
            # Return empty features
            empty_hist = np.zeros((16, 16, 16))
            empty_hog = np.zeros(36)
            return empty_hist, empty_hog, empty_hist, empty_hist
    
    def update(self, frame: np.ndarray, bbox: Dict[str, float]):
        """Update appearance model with new detection"""
        # Extract features
        hist, hog_features, upper_hist, lower_hist = self._extract_features(frame, bbox)
        
        # Initialize if first update
        if self.hist is None:
            self.hist = hist
            self.hog_features = hog_features
            self.upper_hist = upper_hist
            self.lower_hist = lower_hist
            self.history = [(hist, hog_features, upper_hist, lower_hist)]
            return
        
        # Add to history
        self.history.append((hist, hog_features, upper_hist, lower_hist))
        
        # Keep history at fixed size
        if len(self.history) > self.history_size:
            self.history.pop(0)
        
        # Update current histogram as average of history
        self.hist = np.mean([h[0] for h in self.history], axis=0)
        self.hog_features = np.mean([h[1] for h in self.history], axis=0)
        self.upper_hist = np.mean([h[2] for h in self.history], axis=0)
        self.lower_hist = np.mean([h[3] for h in self.history], axis=0)
    
    def compare(self, other) -> float:
        """
        Compare this appearance with another, returning similarity score 0-1
        Uses multiple features with weighted combination
        """
        if self.hist is None or other.hist is None:
            return 0.5  # Neutral score if either model is empty
        
        # 1. Color histogram similarity
        color_sim = cv2.compareHist(self.hist, other.hist, cv2.HISTCMP_BHATTACHARYYA)
        color_sim = np.exp(-color_sim * 5)  # Convert to similarity score
        
        # 2. HOG feature similarity
        hog_dist = np.linalg.norm(self.hog_features - other.hog_features)
        hog_sim = np.exp(-hog_dist * 5)
        
        # 3. Upper/lower body similarity
        upper_sim = cv2.compareHist(self.upper_hist, other.upper_hist, cv2.HISTCMP_BHATTACHARYYA)
        upper_sim = np.exp(-upper_sim * 5)
        
        lower_sim = cv2.compareHist(self.lower_hist, other.lower_hist, cv2.HISTCMP_BHATTACHARYYA)
        lower_sim = np.exp(-lower_sim * 5)
        
        body_sim = 0.6 * upper_sim + 0.4 * lower_sim  # Upper body slightly more important
        
        # Weighted combination
        similarity = (
            self.feature_weights['color'] * color_sim +
            self.feature_weights['hog'] * hog_sim +
            self.feature_weights['upper_lower'] * body_sim
        )
        
        return similarity

class PersonTracker:
    def __init__(self, 
                 max_distance_threshold: float = 100.0, 
                 max_inactive_frames: int = 30,  # Increased from 10 to 30
                 min_hits: int = 3,
                 appearance_weight: float = 0.6,  # Increased from 0.4 to 0.6
                 reid_threshold: float = 0.7):   # New parameter for re-identification
        self.tracks: Dict[int, Dict] = {}  # Track ID -> track info
        self.next_id = 1
        self.max_distance_threshold = max_distance_threshold
        self.max_inactive_frames = max_inactive_frames  # Number of frames to keep inactive tracks
        self.min_hits = min_hits  # Minimum hits needed to consider a track confirmed
        self.appearance_weight = appearance_weight  # Weight for appearance in matching score
        self.position_weight = 1.0 - appearance_weight  # Weight for position in matching score
        self.reid_threshold = reid_threshold  # Threshold for re-identification
        self.debug_frames: List = [] if DEBUG else None
        self.frame_count = 0
        
        # Track history for re-identification
        self.lost_tracks: Dict[int, Dict] = {}  # Store recently lost tracks for re-identification
        self.max_lost_track_age = 100  # Keep lost tracks for this many frames
        
        # Motion consistency tracking
        self.motion_consistency_weight = 0.3  # Weight for motion consistency in matching
        
        # Create debug output directory if needed
        if DEBUG:
            os.makedirs("debug_output", exist_ok=True)
            os.makedirs("debug_output/frames", exist_ok=True)
            os.makedirs("debug_output/tracks", exist_ok=True)
            logger.debug(f"Initialized PersonTracker with max_distance={max_distance_threshold}, " + 
                        f"appearance_weight={appearance_weight}")
    
    def _calculate_center(self, bbox: Dict[str, float]) -> Tuple[float, float]:
        """Calculate center point from bounding box"""
        x = (bbox['xmin'] + bbox['xmax']) / 2
        y = (bbox['ymin'] + bbox['ymax']) / 2
        return (x, y)
    
    def _calculate_size(self, bbox: Dict[str, float]) -> float:
        """Calculate bounding box size (area)"""
        width = bbox['xmax'] - bbox['xmin']
        height = bbox['ymax'] - bbox['ymin']
        return width * height
    
    def _calculate_aspect_ratio(self, bbox: Dict[str, float]) -> float:
        """Calculate bounding box aspect ratio (width/height)"""
        width = bbox['xmax'] - bbox['xmin']
        height = bbox['ymax'] - bbox['ymin']
        if height == 0:
            return 1.0
        return width / height
    
    def _calculate_iou(self, bbox1: Dict[str, float], bbox2: Dict[str, float]) -> float:
        """Calculate Intersection over Union between two bounding boxes"""
        # Calculate intersection
        xmin = max(bbox1['xmin'], bbox2['xmin'])
        ymin = max(bbox1['ymin'], bbox2['ymin'])
        xmax = min(bbox1['xmax'], bbox2['xmax'])
        ymax = min(bbox1['ymax'], bbox2['ymax'])
        
        if xmax <= xmin or ymax <= ymin:
            return 0.0
        
        intersection = (xmax - xmin) * (ymax - ymin)
        
        # Calculate areas
        area1 = (bbox1['xmax'] - bbox1['xmin']) * (bbox1['ymax'] - bbox1['ymin'])
        area2 = (bbox2['xmax'] - bbox2['xmin']) * (bbox2['ymax'] - bbox2['ymin'])
        
        # Calculate IoU
        union = area1 + area2 - intersection
        if union <= 0:
            return 0.0
        
        return intersection / union
    
    def _calculate_matching_cost(self, 
                                center: Tuple[float, float], 
                                person: Dict, 
                                track_id: int,
                                frame: np.ndarray) -> float:
        """Calculate cost for matching a detection to a track"""
        track = self.tracks[track_id]
        
        # 1. Position cost - normalized Euclidean distance
        predicted_pos = track['kalman'].predict()
        distance = np.linalg.norm(np.array(center) - predicted_pos)
        position_cost = min(1.0, distance / self.max_distance_threshold)
        
        # 2. Appearance cost
        # Extract appearance of current detection
        new_appearance = AppearanceModel(frame, person.get('bounding_box', {}))
        
        # Compare with track's appearance
        if 'appearance' in track:
            appearance_cost = 1.0 - track['appearance'].compare(new_appearance)
        else:
            appearance_cost = 0.5  # Neutral if no appearance yet
        
        # 3. Size and aspect ratio consistency
        size_cost = 0.0
        aspect_cost = 0.0
        if 'current_bbox' in track and 'bounding_box' in person:
            # Size consistency
            track_size = self._calculate_size(track['current_bbox'])
            det_size = self._calculate_size(person['bounding_box'])
            if track_size > 0 and det_size > 0:
                size_ratio = abs(track_size - det_size) / max(track_size, det_size)
                size_cost = min(1.0, size_ratio)
            
            # Aspect ratio consistency
            track_aspect = self._calculate_aspect_ratio(track['current_bbox'])
            det_aspect = self._calculate_aspect_ratio(person['bounding_box'])
            aspect_diff = abs(track_aspect - det_aspect)
            aspect_cost = min(1.0, aspect_diff / 2.0)  # Normalize to [0,1]
        
        # 4. Motion consistency - penalize sudden direction changes
        motion_cost = 0.0
        if len(track.get('position_history', [])) >= 2:
            # Get last two positions and current predicted position
            prev_positions = track['position_history'][-2:]
            if len(prev_positions) >= 2:
                # Calculate previous velocity vector
                prev_vel = np.array(prev_positions[1]) - np.array(prev_positions[0])
                # Calculate current velocity vector (predicted to detection)
                curr_vel = np.array(center) - np.array(prev_positions[1])
                
                # Normalize vectors
                prev_vel_norm = np.linalg.norm(prev_vel)
                curr_vel_norm = np.linalg.norm(curr_vel)
                
                if prev_vel_norm > 0 and curr_vel_norm > 0:
                    # Calculate cosine similarity between velocity vectors
                    cos_sim = np.dot(prev_vel, curr_vel) / (prev_vel_norm * curr_vel_norm)
                    # Convert to a cost (1 = opposite direction, 0 = same direction)
                    motion_cost = (1.0 - cos_sim) / 2.0
        
        # 5. IoU cost (if available)
        iou_cost = 0.0
        if 'current_bbox' in track and 'bounding_box' in person:
            iou = self._calculate_iou(track['current_bbox'], person['bounding_box'])
            iou_cost = 1.0 - iou  # Convert to cost (0 = perfect overlap)
        
        # 6. Quality-weighted combined cost
        # Use track quality to determine reliability of track's prediction
        quality = track['kalman'].get_track_quality()
        
        # Combine all costs with appropriate weights
        position_weight = self.position_weight * 0.7  # 70% of position weight
        appearance_weight = self.appearance_weight
        iou_weight = self.position_weight * 0.3      # 30% of position weight
        size_aspect_weight = 0.1
        motion_weight = self.motion_consistency_weight
        
        # Ensure weights sum to 1
        total_weight = position_weight + appearance_weight + iou_weight + size_aspect_weight + motion_weight
        position_weight /= total_weight
        appearance_weight /= total_weight
        iou_weight /= total_weight
        size_aspect_weight /= total_weight
        motion_weight /= total_weight
        
        weighted_cost = (
            position_weight * position_cost +
            appearance_weight * appearance_cost +
            iou_weight * iou_cost +
            size_aspect_weight * (0.7 * size_cost + 0.3 * aspect_cost) +
            motion_weight * motion_cost
        )
        
        # Apply quality factor - when quality is low, rely more on appearance
        final_cost = quality * weighted_cost + (1 - quality) * (
            0.3 * position_cost + 0.7 * appearance_cost
        )
        
        if DEBUG and track['active']:
            logger.debug(f"Match cost for detection at {center} to track {track_id}: " +
                        f"pos={position_cost:.3f}, app={appearance_cost:.3f}, " +
                        f"iou={iou_cost:.3f}, size/aspect={size_cost:.3f}/{aspect_cost:.3f}, " +
                        f"motion={motion_cost:.3f}, quality={quality:.3f}, final={final_cost:.3f}")
        
        return final_cost
    
    def _compute_cost_matrix(self, detections: List[Tuple], frame: np.ndarray) -> Tuple[np.ndarray, List[int]]:
        """Compute cost matrix for Hungarian assignment"""
        # Get active track IDs
        track_ids = [tid for tid, track in self.tracks.items() 
                    if track['active'] or track['kalman'].time_since_update < self.max_inactive_frames]
        
        if not track_ids or not detections:
            return np.array([]), []
        
        # Build cost matrix
        cost_matrix = np.zeros((len(track_ids), len(detections)))
        
        for i, track_id in enumerate(track_ids):
            for j, (center, person) in enumerate(detections):
                cost = self._calculate_matching_cost(center, person, track_id, frame)
                cost_matrix[i, j] = cost
        
        return cost_matrix, track_ids
    
    def _attempt_reid(self, detection: Tuple, frame: np.ndarray) -> Optional[int]:
        """
        Attempt to re-identify a lost track for this detection
        Returns track_id if successful, None otherwise
        """
        center, person = detection
        new_appearance = AppearanceModel(frame, person.get('bounding_box', {}))
        
        best_match_id = None
        best_match_score = 0.0
        
        # Check all lost tracks
        for track_id, track in self.lost_tracks.items():
            # Skip if lost for too long
            if track['frames_lost'] > self.max_lost_track_age:
                continue
            
            # Compare appearances
            if 'appearance' in track:
                similarity = track['appearance'].compare(new_appearance)
                
                # If similarity is high enough, consider it a match
                if similarity > self.reid_threshold and similarity > best_match_score:
                    best_match_id = track_id
                    best_match_score = similarity
        
        if best_match_id is not None and DEBUG:
            logger.debug(f"Re-identified lost track {best_match_id} with similarity {best_match_score:.3f}")
        
        return best_match_id
    
    def update(self, frame: np.ndarray, people: List[Dict]) -> Dict[int, Dict]:
        """Update tracks with new detections using Hungarian algorithm for global assignment"""
        self.frame_count += 1
        current_centers = {}
        new_detections = []
        
        # First, predict new locations for all tracks
        for track_id, track in self.tracks.items():
            track['kalman'].predict()  # Just update internal state
            track['active'] = False    # Will be set to True if matched
        
        # Calculate centers for all detections
        for person in people:
            bbox = person.get('bounding_box')
            if not bbox:
                continue
            center = self._calculate_center(bbox)
            new_detections.append((center, person))
        
        # Sort detections by y-coordinate (top to bottom) for more stable reference
        # This helps maintain consistency in how we assign new IDs
        new_detections.sort(key=lambda x: x[0][1])
        
        # Compute cost matrix for assignment
        result = self._compute_cost_matrix(new_detections, frame)
        if len(result) == 0:
            cost_matrix, track_ids = np.array([]), []
        else:
            cost_matrix, track_ids = result
        
        matched_indices = []
        unmatched_detections = list(range(len(new_detections)))
        unmatched_tracks = list(range(len(track_ids)))
        
        # If we have both tracks and detections, solve the assignment problem
        if len(cost_matrix) > 0:
            # Apply the Hungarian algorithm to find the optimal assignment
            # This makes sure we get the globally optimal assignment of tracks to detections
            row_ind, col_ind = linear_sum_assignment(cost_matrix)
            
            # Filter out assignments with high cost
            for r, c in zip(row_ind, col_ind):
                if cost_matrix[r, c] > 0.8:  # Reduced threshold from 0.9 to 0.8 for more strict matching
                    if DEBUG:
                        logger.debug(f"Rejecting assignment of track {track_ids[r]} to detection {c} with cost {cost_matrix[r, c]:.3f}")
                    continue
                
                matched_indices.append((r, c))
                unmatched_detections.remove(c)
                unmatched_tracks.remove(r)
        
        # Update matched tracks
        for track_idx, detection_idx in matched_indices:
            track_id = track_ids[track_idx]
            center, person = new_detections[detection_idx]
            
            # Update track
            track = self.tracks[track_id]
            track['active'] = True
            track['kalman'].update(center[0], center[1])
            track['current_bbox'] = person['bounding_box']
            track['activities'] = person.get('activities', [])
            track['last_seen'] = datetime.now()
            
            # Update position history
            if 'position_history' not in track:
                track['position_history'] = []
            track['position_history'].append(center)
            # Keep only last 10 positions
            if len(track['position_history']) > 10:
                track['position_history'] = track['position_history'][-10:]
            
            # Update appearance model
            if 'appearance' in track:
                track['appearance'].update(frame, person['bounding_box'])
            else:
                track['appearance'] = AppearanceModel(frame, person['bounding_box'])
            
            # Store track ID in person data for database storage
            person['track_id'] = track_id
            
            current_centers[track_id] = center
            
            if DEBUG:
                logger.debug(f"Updated track {track_id} with detection at {center}")
        
        # Try to re-identify lost tracks for unmatched detections
        reid_detections = []
        for detection_idx in unmatched_detections.copy():
            detection = new_detections[detection_idx]
            
            # Try to re-identify
            reid_track_id = self._attempt_reid(detection, frame)
            
            if reid_track_id is not None:
                # Successfully re-identified
                center, person = detection
                
                # Restore track from lost tracks
                lost_track = self.lost_tracks.pop(reid_track_id)
                
                # Create new Kalman filter (the old one might be too diverged)
                kalman = AdvancedKalmanFilter()
                kalman.init(center[0], center[1])
                kalman.hits = lost_track['kalman'].hits  # Preserve hit count
                
                # Create restored track
                self.tracks[reid_track_id] = {
                    'kalman': kalman,
                    'active': True,
                    'current_bbox': person['bounding_box'],
                    'activities': person.get('activities', []),
                    'appearance': lost_track['appearance'],  # Keep the appearance model
                    'first_seen': lost_track['first_seen'],  # Keep original first seen time
                    'last_seen': datetime.now(),
                    'position_history': [center]  # Start fresh position history
                }
                
                # Update appearance with current frame
                self.tracks[reid_track_id]['appearance'].update(frame, person['bounding_box'])
                
                # Store track ID in person data
                person['track_id'] = reid_track_id
                
                current_centers[reid_track_id] = center
                
                # Remove from unmatched detections
                unmatched_detections.remove(detection_idx)
                
                if DEBUG:
                    logger.debug(f"Re-identified track {reid_track_id} at position {center}")
                
                # Add to re-identified detections
                reid_detections.append(detection_idx)
        
        # Create new tracks for remaining unmatched detections
        for detection_idx in unmatched_detections:
            center, person = new_detections[detection_idx]
            
            # Create new track
            kalman = AdvancedKalmanFilter()
            kalman.init(center[0], center[1])
            
            new_track = {
                'kalman': kalman,
                'active': True,
                'current_bbox': person['bounding_box'],
                'activities': person.get('activities', []),
                'appearance': AppearanceModel(frame, person['bounding_box']),
                'first_seen': datetime.now(),
                'last_seen': datetime.now(),
                'position_history': [center]
            }
            
            # Use the track ID from person data if available, otherwise assign a new one
            if 'track_id' in person and person['track_id'] > 0:
                track_id = person['track_id']
                self.next_id = max(self.next_id, track_id + 1)
            else:
                track_id = self.next_id
                self.next_id += 1
                person['track_id'] = track_id
            
            self.tracks[track_id] = new_track
            current_centers[track_id] = center
            
            if DEBUG:
                logger.debug(f"Created new track {track_id} at position {center}")
        
        # Move unmatched tracks to lost tracks
        for track_idx in unmatched_tracks:
            track_id = track_ids[track_idx]
            track = self.tracks[track_id]
            
            # Only move to lost tracks if it was previously active and has enough hits
            if track['kalman'].hits >= self.min_hits:
                # Copy to lost tracks
                self.lost_tracks[track_id] = track.copy()
                self.lost_tracks[track_id]['frames_lost'] = 0
                
                if DEBUG:
                    logger.debug(f"Track {track_id} moved to lost tracks")
        
        # Update lost tracks counter
        for track_id in list(self.lost_tracks.keys()):
            self.lost_tracks[track_id]['frames_lost'] += 1
        
        # Clean up old inactive tracks
        tracks_to_delete = []
        lost_tracks_to_delete = []
        current_time = datetime.now()
        
        # Clean up active tracks
        for track_id, track in self.tracks.items():
            # If track was not matched
            if not track['active']:
                # Consider the track lost after max_inactive_frames
                if track['kalman'].time_since_update > self.max_inactive_frames:
                    tracks_to_delete.append(track_id)
        
        # Clean up lost tracks
        for track_id, track in self.lost_tracks.items():
            if track['frames_lost'] > self.max_lost_track_age:
                lost_tracks_to_delete.append(track_id)
        
        # Delete old tracks
        for track_id in tracks_to_delete:
            del self.tracks[track_id]
        
        # Delete old lost tracks
        for track_id in lost_tracks_to_delete:
            del self.lost_tracks[track_id]
        
        if DEBUG:
            self._draw_debug_frame(frame, current_centers)
            self._save_track_info(current_centers)
        
        # Return only active tracks
        return {k: v for k, v in self.tracks.items() if v['active']}
    
    def _draw_debug_frame(self, frame: np.ndarray, current_centers: Dict[int, Tuple[float, float]]):
        """Draw debug visualization on frame"""
        debug_frame = frame.copy()
        height, width = debug_frame.shape[:2]
        
        # Draw each active track
        for track_id, center in current_centers.items():
            # Convert normalized coordinates to pixel coordinates
            px = int(center[0] * width / 1000.0)
            py = int(center[1] * height / 1000.0)
            
            # Draw center point
            cv2.circle(debug_frame, (px, py), 5, (0, 255, 0), -1)
            
            # Draw ID and predicted position
            track = self.tracks[track_id]
            predicted_pos = track['kalman'].predict()
            pred_px = int(predicted_pos[0] * width / 1000.0)
            pred_py = int(predicted_pos[1] * height / 1000.0)
            
            # Draw prediction line
            cv2.line(debug_frame, (px, py), (pred_px, pred_py), (255, 0, 0), 2)
            
            # Draw bounding box
            bbox = track['current_bbox']
            if bbox:
                box_x1 = int(bbox['xmin'] * width / 1000.0)
                box_y1 = int(bbox['ymin'] * height / 1000.0)
                box_x2 = int(bbox['xmax'] * width / 1000.0)
                box_y2 = int(bbox['ymax'] * height / 1000.0)
                
                # Color based on track quality
                quality = track['kalman'].get_track_quality()
                color = (int(255 * (1-quality)), int(255 * quality), 0)  # Red to Green based on quality
                
                cv2.rectangle(debug_frame, (box_x1, box_y1), (box_x2, box_y2), color, 2)
            
            # Draw ID and activities
            quality = track['kalman'].get_track_quality()
            quality_text = f"{quality:.2f}"
            text = f"ID: {track_id} (Q: {quality_text})"
            cv2.putText(debug_frame, text, (px + 10, py), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            
            # Draw activities
            for i, activity in enumerate(track['activities']):
                activity_text = f"{activity['name']}: {activity['confidence']:.2f}"
                cv2.putText(debug_frame, activity_text, (px + 10, py + 20 + i*20),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            
            # Draw position history
            if 'position_history' in track and len(track['position_history']) > 1:
                points = []
                for pos in track['position_history']:
                    points.append((int(pos[0] * width / 1000.0), int(pos[1] * height / 1000.0)))
                
                # Draw trajectory line
                for i in range(1, len(points)):
                    cv2.line(debug_frame, points[i-1], points[i], (0, 0, 255), 2)
        
        # Draw lost tracks
        for track_id, track in self.lost_tracks.items():
            if 'current_bbox' in track:
                bbox = track['current_bbox']
                box_x1 = int(bbox['xmin'] * width / 1000.0)
                box_y1 = int(bbox['ymin'] * height / 1000.0)
                box_x2 = int(bbox['xmax'] * width / 1000.0)
                box_y2 = int(bbox['ymax'] * height / 1000.0)
                
                # Draw dashed rectangle for lost tracks
                dash_length = 5
                for i in range(0, box_x2 - box_x1, dash_length * 2):
                    cv2.line(debug_frame, (box_x1 + i, box_y1), 
                             (min(box_x1 + i + dash_length, box_x2), box_y1), (0, 0, 255), 2)
                    cv2.line(debug_frame, (box_x1 + i, box_y2), 
                             (min(box_x1 + i + dash_length, box_x2), box_y2), (0, 0, 255), 2)
                
                for i in range(0, box_y2 - box_y1, dash_length * 2):
                    cv2.line(debug_frame, (box_x1, box_y1 + i), 
                             (box_x1, min(box_y1 + i + dash_length, box_y2)), (0, 0, 255), 2)
                    cv2.line(debug_frame, (box_x2, box_y1 + i), 
                             (box_x2, min(box_y1 + i + dash_length, box_y2)), (0, 0, 255), 2)
                
                # Draw lost track ID
                text = f"Lost ID: {track_id} ({track['frames_lost']})"
                cv2.putText(debug_frame, text, (box_x1, box_y1 - 10), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
        
        # Save debug frame
        debug_path = f"debug_output/frames/frame_{self.frame_count:04d}.jpg"
        cv2.imwrite(debug_path, debug_frame)
        
        # Store frame info for debug log
        self.debug_frames.append({
            'frame_number': self.frame_count,
            'frame_path': debug_path,
            'active_tracks': len(current_centers),
            'track_ids': list(current_centers.keys()),
            'lost_tracks': list(self.lost_tracks.keys())
        })
    
    def _save_track_info(self, current_centers: Dict[int, Tuple[float, float]]):
        """Save detailed tracking information for debugging"""
        track_info = {
            'frame_number': self.frame_count,
            'timestamp': datetime.now().isoformat(),
            'tracks': {},
            'lost_tracks': {}
        }
        
        for track_id, track in self.tracks.items():
            # Get track quality and state
            quality = track['kalman'].get_track_quality()
            state = track['kalman'].get_state()
            
            track_info['tracks'][str(track_id)] = {
                'active': track['active'],
                'first_seen': track['first_seen'].isoformat(),
                'last_seen': track['last_seen'].isoformat(),
                'current_position': current_centers.get(track_id),
                'predicted_position': state[:2].tolist() if track['active'] else None,
                'velocity': state[2:4].tolist() if track['active'] else None,
                'acceleration': state[4:6].tolist() if track['active'] else None,
                'quality': quality,
                'hits': track['kalman'].hits,
                'time_since_update': track['kalman'].time_since_update,
                'activities': track['activities'],
                'position_history': track.get('position_history', [])
            }
        
        # Add lost tracks info
        for track_id, track in self.lost_tracks.items():
            track_info['lost_tracks'][str(track_id)] = {
                'first_seen': track['first_seen'].isoformat(),
                'last_seen': track['last_seen'].isoformat(),
                'frames_lost': track['frames_lost'],
                'hits': track['kalman'].hits
            }
        
        # Save track info
        with open(f"debug_output/tracks/track_info_{self.frame_count:04d}.json", 'w') as f:
            json.dump(track_info, f, indent=2)
        
        # Save summary every 100 frames
        if self.frame_count % 100 == 0:
            self._save_debug_info()
    
    def _save_debug_info(self):
        """Save debug information to JSON file"""
        if not DEBUG or not self.debug_frames:
            return
            
        debug_info = {
            'timestamp': datetime.now().isoformat(),
            'total_frames': len(self.debug_frames),
            'frames': self.debug_frames
        }
        
        debug_file = f"debug_output/tracker_debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(debug_file, 'w') as f:
            json.dump(debug_info, f, indent=2)
        
        # Clear the frames list after saving
        self.debug_frames = []
        logger.debug(f"Saved debug information to {debug_file}") 