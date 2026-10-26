import cv2
import numpy as np
import os
import argparse
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import matplotlib.pyplot as plt
from collections import deque
import random

import logging
logger = logging.getLogger(__name__)
class MotionTracker:
    """
    A simple motion-based tracker that focuses on maintaining consistent IDs
    based on motion patterns and spatial proximity.
    """
    def __init__(self, 
                max_distance_threshold: float = 50.0,
                max_frames_to_skip: int = 10,
                max_trace_length: int = 10,
                min_detection_confidence: float = 0.5):
        """
        Initialize the motion tracker.
        
        Args:
            max_distance_threshold: Maximum distance between points to consider them the same object
            max_frames_to_skip: Maximum number of frames an object can be missing before it's removed
            max_trace_length: Maximum length of trajectory history to maintain
            min_detection_confidence: Minimum confidence for a detection to be tracked
        """
        self.tracks = []  # List of tracks
        self.next_track_id = 0  # Next available track ID
        self.max_distance_threshold = max_distance_threshold
        self.max_frames_to_skip = max_frames_to_skip
        self.max_trace_length = max_trace_length
        self.min_detection_confidence = min_detection_confidence
        self.frame_count = 0
        
        # Generate a set of distinct colors for visualization
        self.colors = self._generate_colors(100)  # Pre-generate 100 colors
        
        # Create output directory
        os.makedirs("motion_tracking_output", exist_ok=True)
    
    def _generate_colors(self, num_colors: int) -> List[Tuple[int, int, int]]:
        """Generate a list of distinct colors for visualization."""
        colors = []
        for i in range(num_colors):
            # Use HSV color space to generate evenly distributed colors
            hue = i / num_colors
            # Convert to RGB
            rgb = plt.cm.hsv(hue)[:3]  # Get RGB values (ignore alpha)
            # Convert to BGR (OpenCV format) and scale to 0-255
            bgr = (int(rgb[2] * 255), int(rgb[1] * 255), int(rgb[0] * 255))
            colors.append(bgr)
        
        # Shuffle colors to make adjacent IDs have distinct colors
        random.shuffle(colors)
        return colors
    
    def _get_color(self, track_id: int) -> Tuple[int, int, int]:
        """Get a color for a track ID."""
        return self.colors[track_id % len(self.colors)]
    
    def _calculate_distance(self, point1: Tuple[int, int], point2: Tuple[int, int]) -> float:
        """Calculate Euclidean distance between two points."""
        return np.sqrt((point1[0] - point2[0])**2 + (point1[1] - point2[1])**2)
    
    def _predict_next_position(self, track: Dict) -> Tuple[int, int]:
        """
        Predict the next position of a track based on its velocity.
        Uses simple linear prediction based on the last two positions.
        """
        trace = track['trace']
        if len(trace) < 2:
            return trace[-1]  # Return the last position if we don't have enough history
        
        # Calculate velocity from the last two positions
        last_pos = trace[-1]
        prev_pos = trace[-2]
        velocity_x = last_pos[0] - prev_pos[0]
        velocity_y = last_pos[1] - prev_pos[1]
        
        # Predict next position
        predicted_x = int(last_pos[0] + velocity_x)
        predicted_y = int(last_pos[1] + velocity_y)
        
        return (predicted_x, predicted_y)
    
    def update(self, detections: List[Tuple[int, int, float]]) -> List[Dict]:
        """
        Update tracks with new detections.
        
        Args:
            detections: List of (x, y, confidence) tuples representing detected objects
            
        Returns:
            List of active tracks
        """
        self.frame_count += 1
        
        # Filter detections by confidence
        filtered_detections = [d for d in detections if d[2] >= self.min_detection_confidence]
        
        # If we have no tracks yet, initialize with all detections
        if not self.tracks:
            for x, y, conf in filtered_detections:
                self.tracks.append({
                    'id': self.next_track_id,
                    'trace': deque([(x, y)], maxlen=self.max_trace_length),
                    'skipped_frames': 0,
                    'active': True,
                    'confidence': conf
                })
                self.next_track_id += 1
            return self.tracks
        
        # Predict new locations for all tracks
        for track in self.tracks:
            track['predicted_pos'] = self._predict_next_position(track)
            track['matched'] = False  # Reset matched flag
        
        # Match detections to existing tracks
        assignment = self._assign_detections_to_tracks(filtered_detections)
        
        # Update matched tracks
        for track_idx, detection_idx in assignment:
            x, y, conf = filtered_detections[detection_idx]
            track = self.tracks[track_idx]
            
            # Update track with new detection
            track['trace'].append((x, y))
            track['skipped_frames'] = 0
            track['active'] = True
            track['matched'] = True
            track['confidence'] = conf
        
        # Handle unmatched tracks
        for i, track in enumerate(self.tracks):
            if not track['matched']:
                track['skipped_frames'] += 1
                if track['skipped_frames'] > self.max_frames_to_skip:
                    track['active'] = False
        
        # Create new tracks for unmatched detections
        for i, detection in enumerate(filtered_detections):
            if i not in [det_idx for _, det_idx in assignment]:
                x, y, conf = detection
                self.tracks.append({
                    'id': self.next_track_id,
                    'trace': deque([(x, y)], maxlen=self.max_trace_length),
                    'skipped_frames': 0,
                    'active': True,
                    'confidence': conf,
                    'matched': True
                })
                self.next_track_id += 1
        
        # Return only active tracks
        return [track for track in self.tracks if track['active']]
    
    def _assign_detections_to_tracks(self, detections: List[Tuple[int, int, float]]) -> List[Tuple[int, int]]:
        """
        Assign detections to tracks using a greedy approach based on distance.
        
        Args:
            detections: List of (x, y, confidence) tuples
            
        Returns:
            List of (track_idx, detection_idx) pairs
        """
        if not detections or not self.tracks:
            return []
        
        # Calculate distance matrix
        distance_matrix = np.zeros((len(self.tracks), len(detections)))
        for i, track in enumerate(self.tracks):
            for j, (x, y, _) in enumerate(detections):
                distance = self._calculate_distance(track['predicted_pos'], (x, y))
                distance_matrix[i, j] = distance
        
        # Assign detections to tracks greedily
        assignments = []
        
        # Create a copy of the distance matrix to modify
        distance_copy = distance_matrix.copy()
        
        # While there are still possible assignments
        while True:
            # Find the minimum distance
            i, j = np.unravel_index(distance_copy.argmin(), distance_copy.shape)
            min_dist = distance_copy[i, j]
            
            # If the minimum distance is above threshold, we're done
            if min_dist > self.max_distance_threshold:
                break
            
            # Add the assignment
            assignments.append((i, j))
            
            # Mark this pair as unavailable (set to a large value)
            distance_copy[i, :] = float('inf')
            distance_copy[:, j] = float('inf')
            
            # If all tracks or detections are assigned, we're done
            if np.all(distance_copy == float('inf')):
                break
        
        return assignments
    
    def draw_tracks(self, frame: np.ndarray) -> np.ndarray:
        """
        Draw tracks on the frame.
        
        Args:
            frame: Input frame
            
        Returns:
            Frame with tracks drawn
        """
        result = frame.copy()
        
        # Draw each active track
        for track in self.tracks:
            if not track['active']:
                continue
            
            # Get track color
            color = self._get_color(track['id'])
            
            # Draw trajectory (line connecting past positions)
            points = list(track['trace'])
            for i in range(1, len(points)):
                cv2.line(result, points[i-1], points[i], color, 2)
            
            # Draw current position (larger dot)
            if points:
                current_pos = points[-1]
                cv2.circle(result, current_pos, 6, color, -1)
                
                # Draw ID near the current position
                cv2.putText(result, f"ID: {track['id']}", 
                           (current_pos[0] + 10, current_pos[1]), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        
        # Add frame counter
        cv2.putText(result, f"Frame: {self.frame_count}", (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        return result

def detect_green_dots(image: np.ndarray, min_radius: int = 3, max_radius: int = 15) -> List[Tuple[int, int, float]]:
    """
    Detect green dots in the image.
    
    Args:
        image: Input image
        min_radius: Minimum radius of dots to detect
        max_radius: Maximum radius of dots to detect
        
    Returns:
        List of (x, y, confidence) tuples for detected dots
    """
    # Convert to HSV for better color filtering
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    
    # Define range for green color
    lower_green = np.array([40, 50, 50])
    upper_green = np.array([80, 255, 255])
    
    # Create a mask for green color
    mask = cv2.inRange(hsv, lower_green, upper_green)
    
    # Apply morphological operations to remove noise
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    
    # Find contours in the mask
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # Filter contours by size and circularity
    detections = []
    for contour in contours:
        # Calculate area and perimeter
        area = cv2.contourArea(contour)
        perimeter = cv2.arcLength(contour, True)
        
        # Skip if too small
        if area < np.pi * min_radius**2:
            continue
        
        # Skip if too large
        if area > np.pi * max_radius**2:
            continue
        
        # Calculate circularity (1.0 for a perfect circle)
        circularity = 4 * np.pi * area / (perimeter**2) if perimeter > 0 else 0
        
        # Skip if not circular enough
        if circularity < 0.7:
            continue
        
        # Calculate center
        M = cv2.moments(contour)
        if M["m00"] > 0:
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
            
            # Use circularity as confidence
            confidence = circularity
            
            detections.append((cx, cy, confidence))
    
    return detections

def process_video(video_path: str, output_path: str = None, show_video: bool = False):
    """
    Process a video file with the motion tracker.
    
    Args:
        video_path: Path to the video file
        output_path: Path to save the output video (None to skip saving)
        show_video: Whether to display the video during processing
    """
    # Open the video file
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.info(f"Error: Could not open video file {video_path}")
        return
    
    # Get video properties
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    logger.info(f"Video properties: {width}x{height}, {fps} FPS, {total_frames} frames")
    
    # Create video writer if output path is specified
    writer = None
    if output_path:
        fourcc = cv2.VideoWriter_fourcc(*'XVID')
        writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
    
    # Initialize the tracker
    tracker = MotionTracker(
        max_distance_threshold=50.0,
        max_frames_to_skip=10,
        max_trace_length=10
    )
    
    frame_idx = 0
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        # Detect green dots in the frame
        detections = detect_green_dots(frame)
        
        # Update the tracker with new detections
        active_tracks = tracker.update(detections)
        
        # Draw tracks on the frame
        result_frame = tracker.draw_tracks(frame)
        
        # Save the frame if output directory is specified
        if frame_idx % 5 == 0:  # Save every 5th frame
            cv2.imwrite(f"motion_tracking_output/frame_{frame_idx:04d}.jpg", result_frame)
        
        # Write to output video if specified
        if writer:
            writer.write(result_frame)
        
        # Display the frame if requested
        if show_video:
            cv2.imshow('Motion Tracking', result_frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        
        # Print progress
        if frame_idx % 10 == 0:
            logger.info(f"Processing frame {frame_idx}/{total_frames} ({frame_idx/total_frames*100:.1f}%)")
        
        frame_idx += 1
    
    # Release resources
    cap.release()
    if writer:
        writer.release()
    if show_video:
        cv2.destroyAllWindows()
    
    logger.info(f"Processed {frame_idx} frames. Output saved to {output_path}")

def process_image_sequence(image_dir: str, pattern: str = "*.jpg", output_path: str = None, show_images: bool = False):
    """
    Process a sequence of images with the motion tracker.
    
    Args:
        image_dir: Directory containing the images
        pattern: Glob pattern to match image files
        output_path: Path to save the output video (None to skip saving)
        show_images: Whether to display the images during processing
    """
    # Get list of image files
    image_files = sorted(list(Path(image_dir).glob(pattern)))
    if not image_files:
        logger.info(f"Error: No images found in {image_dir} matching pattern {pattern}")
        return
    
    logger.info(f"Found {len(image_files)} images")
    
    # Read the first image to get dimensions
    first_image = cv2.imread(str(image_files[0]))
    if first_image is None:
        logger.info(f"Error: Could not read image {image_files[0]}")
        return
    
    height, width = first_image.shape[:2]
    
    # Create video writer if output path is specified
    writer = None
    if output_path:
        fourcc = cv2.VideoWriter_fourcc(*'XVID')
        writer = cv2.VideoWriter(output_path, fourcc, 10, (width, height))  # Assume 10 FPS
    
    # Initialize the tracker
    tracker = MotionTracker(
        max_distance_threshold=50.0,
        max_frames_to_skip=5,
        max_trace_length=10
    )
    
    for i, image_file in enumerate(image_files):
        # Read the image
        frame = cv2.imread(str(image_file))
        if frame is None:
            logger.info(f"Warning: Could not read image {image_file}")
            continue
        
        # Detect green dots in the frame
        detections = detect_green_dots(frame)
        
        # Update the tracker with new detections
        active_tracks = tracker.update(detections)
        
        # Draw tracks on the frame
        result_frame = tracker.draw_tracks(frame)
        
        # Save the frame
        output_filename = f"motion_tracking_output/tracked_{image_file.name}"
        cv2.imwrite(output_filename, result_frame)
        
        # Write to output video if specified
        if writer:
            writer.write(result_frame)
        
        # Display the frame if requested
        if show_images:
            cv2.imshow('Motion Tracking', result_frame)
            if cv2.waitKey(100) & 0xFF == ord('q'):  # Wait 100ms between frames
                break
        
        # Print progress
        if i % 5 == 0 or i == len(image_files) - 1:
            logger.info(f"Processing image {i+1}/{len(image_files)} ({(i+1)/len(image_files)*100:.1f}%)")
    
    # Release resources
    if writer:
        writer.release()
    if show_images:
        cv2.destroyAllWindows()
    
    logger.info(f"Processed {len(image_files)} images. Results saved to motion_tracking_output/")

def process_single_image(image_path: str):
    """
    Process a single image to detect green dots.
    
    Args:
        image_path: Path to the image file
    """
    # Read the image
    image = cv2.imread(image_path)
    if image is None:
        logger.info(f"Error: Could not read image {image_path}")
        return
    
    # Detect green dots
    detections = detect_green_dots(image)
    
    # Draw detections on the image
    result = image.copy()
    for x, y, conf in detections:
        cv2.circle(result, (x, y), 10, (0, 0, 255), -1)  # Red circle
        cv2.putText(result, f"Conf: {conf:.2f}", (x + 10, y), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
    
    # Save the result
    output_path = "motion_tracking_output/detected_dots.jpg"
    cv2.imwrite(output_path, result)
    
    logger.info(f"Detected {len(detections)} green dots. Result saved to {output_path}")
    logger.info(f"Detected points: {detections}")

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Motion-based object tracker")
    parser.add_argument("input", help="Input video file, image directory, or single image")
    parser.add_argument("--output", help="Output video file (optional)")
    parser.add_argument("--mode", choices=["video", "images", "single"], 
                       help="Processing mode (auto-detected if not specified)")
    parser.add_argument("--pattern", default="*.jpg", help="Image file pattern for image sequence mode")
    parser.add_argument("--show", action="store_true", help="Show video/images during processing")
    
    args = parser.parse_args()
    
    # Create output directory
    os.makedirs("motion_tracking_output", exist_ok=True)
    
    # Determine processing mode if not specified
    if not args.mode:
        input_path = Path(args.input)
        if input_path.is_file():
            # Check if it's a video file
            video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.wmv']
            if input_path.suffix.lower() in video_extensions:
                args.mode = "video"
            else:
                args.mode = "single"
        elif input_path.is_dir():
            args.mode = "images"
        else:
            logger.info(f"Error: Input path {args.input} does not exist")
            return
    
    # Process based on mode
    if args.mode == "video":
        process_video(args.input, args.output, args.show)
    elif args.mode == "images":
        process_image_sequence(args.input, args.pattern, args.output, args.show)
    elif args.mode == "single":
        process_single_image(args.input)

if __name__ == "__main__":
    main() 