#!/usr/bin/env python3
"""
Shot Detector Viewer — GUI tool to select and analyze a video for detected shots.

Shows a video file with frame-by-frame detection, highlighting frames where SHOT_FIRED
was detected by the engine.
"""

import asyncio
import base64
import json
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
from typing import Optional, Dict, List, Any
import cv2
import numpy as np
import httpx
from PIL import Image, ImageTk


class ShotDetectorViewer:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Shot Detector Viewer")
        self.root.geometry("1200x800")
        
        self.video_path: Optional[str] = None
        self.cap: Optional[cv2.VideoCapture] = None
        self.is_playing = False
        self.is_analyzing = False
        self.current_frame_idx = 0
        self.total_frames = 0
        self.fps = 0.0
        self.frame_width = 0
        self.frame_height = 0
        
        self.auth_token: Optional[str] = None
        self.engine_url = "http://127.0.0.1:9000/api"
        
        # Shot detection results: frame_idx -> {confidence, diff_area, diff_ratio, line_count}
        self.detected_shots: Dict[int, Dict[str, Any]] = {}
        self.frame_images: List[np.ndarray] = []  # Cache frames for consecutive-pair analysis
        
        self._setup_ui()
    
    def _setup_ui(self):
        # Top control panel
        control_frame = tk.Frame(self.root)
        control_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)
        
        tk.Button(control_frame, text="Select Video", command=self._select_video).pack(side=tk.LEFT, padx=5)
        tk.Button(control_frame, text="Analyze", command=self._start_analysis).pack(side=tk.LEFT, padx=5)
        tk.Button(control_frame, text="Play", command=self._toggle_playback).pack(side=tk.LEFT, padx=5)
        tk.Button(control_frame, text="Reset", command=self._reset).pack(side=tk.LEFT, padx=5)
        
        self.video_label = tk.Label(control_frame, text="No video selected", fg="gray")
        self.video_label.pack(side=tk.LEFT, padx=10)
        
        self.status_label = tk.Label(control_frame, text="Status: Ready", fg="blue")
        self.status_label.pack(side=tk.LEFT, padx=10)
        
        # Video canvas
        canvas_frame = tk.Frame(self.root)
        canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.canvas = tk.Label(canvas_frame, bg="black")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # Right panel: info + timeline
        right_frame = tk.Frame(self.root, width=250, bg="lightgray")
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, padx=10, pady=10)
        right_frame.pack_propagate(False)
        
        tk.Label(right_frame, text="Frame Info", font=("Arial", 12, "bold"), bg="lightgray").pack(pady=5)
        self.info_text = tk.Text(right_frame, height=10, width=30, font=("Courier", 9))
        self.info_text.pack(padx=5, pady=5, fill=tk.BOTH)
        
        tk.Label(right_frame, text="Detected Shots", font=("Arial", 12, "bold"), bg="lightgray").pack(pady=5)
        self.shots_listbox = tk.Listbox(right_frame, height=15, font=("Courier", 8))
        self.shots_listbox.pack(padx=5, pady=5, fill=tk.BOTH, expand=True)
        self.shots_listbox.bind('<<ListboxSelect>>', self._on_shot_selected)
        
        # Slider for frame navigation
        slider_frame = tk.Frame(self.root)
        slider_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=5)
        
        tk.Label(slider_frame, text="Frame:").pack(side=tk.LEFT, padx=5)
        self.frame_slider = tk.Scale(slider_frame, orient=tk.HORIZONTAL, from_=0, to=100, 
                                      command=self._on_slider_change)
        self.frame_slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        self.frame_count_label = tk.Label(slider_frame, text="0 / 0")
        self.frame_count_label.pack(side=tk.LEFT, padx=5)
    
    def _select_video(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("Video files", "*.mp4 *.avi *.mov *.mkv"), ("All files", "*.*")]
        )
        if not file_path:
            return
        
        self.video_path = file_path
        self.video_label.config(text=f"Video: {Path(file_path).name}", fg="black")
        self._reset()
        
        # Load video metadata
        self.cap = cv2.VideoCapture(file_path)
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.frame_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.frame_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        self.frame_slider.config(to=max(1, self.total_frames - 1))
        self.frame_count_label.config(text=f"0 / {self.total_frames}")
        
        # Display first frame
        self._load_and_display_frame(0)
        self.status_label.config(text=f"Status: Ready (FPS: {self.fps:.1f}, Frames: {self.total_frames})", fg="blue")
    
    def _load_and_display_frame(self, frame_idx: int):
        if not self.cap:
            return
        
        self.current_frame_idx = max(0, min(frame_idx, self.total_frames - 1))
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.current_frame_idx)
        ret, frame = self.cap.read()
        
        if not ret:
            return
        
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Draw shot detection annotation if this frame has a detection
        if self.current_frame_idx in self.detected_shots:
            shot_info = self.detected_shots[self.current_frame_idx]
            confidence = shot_info.get("confidence", 0.0)
            lines = shot_info.get("lines", [])
            
            # Debug output
            print(f"Frame {self.current_frame_idx}: Found {len(lines)} lines, frame shape: {frame_rgb.shape}")
            for i, line in enumerate(lines):
                print(f"  Line {i}: {line}")
            
            # Draw detected arrow lines (green/lime)
            arrow_color = (0, 255, 0)  # Green in RGB
            line_thickness = 3
            for line in lines:
                if len(line) == 4:
                    x1, y1, x2, y2 = line
                    print(f"  Drawing line from ({x1},{y1}) to ({x2},{y2})")
                    cv2.line(frame_rgb, (int(x1), int(y1)), (int(x2), int(y2)), arrow_color, line_thickness)
            
            # Draw red border and label
            h, w = frame_rgb.shape[:2]
            border_thickness = 5
            border_color = (255, 0, 0)  # Red in RGB
            # cv2.rectangle(frame_rgb, (0, 0), (w - 1, h - 1), border_color, border_thickness)
            
            label = f"SHOT FIRED ({confidence:.1%})"
            cv2.putText(frame_rgb, label, (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.2, border_color, 3)
        
        # Resize frame for display (max 800x600)
        display_width, display_height = 800, 600
        scale = min(display_width / frame_rgb.shape[1], display_height / frame_rgb.shape[0])
        display_frame = cv2.resize(frame_rgb, (int(frame_rgb.shape[1] * scale), int(frame_rgb.shape[0] * scale)))
        
        img = Image.fromarray(display_frame)
        photo = ImageTk.PhotoImage(img)
        self.canvas.config(image=photo)
        self.canvas.image = photo
        
        # Update frame counter and slider
        self.frame_count_label.config(text=f"{self.current_frame_idx} / {self.total_frames}")
        self.frame_slider.set(self.current_frame_idx)
        
        # Update info panel
        duration_sec = self.current_frame_idx / self.fps if self.fps > 0 else 0
        self.info_text.config(state=tk.NORMAL)
        self.info_text.delete("1.0", tk.END)
        info = f"""Frame: {self.current_frame_idx}
Time: {duration_sec:.2f}s
Size: {self.frame_width}x{self.frame_height}
FPS: {self.fps:.1f}

"""
        if self.current_frame_idx in self.detected_shots:
            shot = self.detected_shots[self.current_frame_idx]
            info += f"🎯 SHOT DETECTED\n"
            info += f"Confidence: {shot.get('confidence', 0.0):.1%}\n"
            info += f"Area: {shot.get('diff_area', 0):.0f} px\n"
            info += f"Arrow Lines: {shot.get('line_count', 0)}\n"
            lines = shot.get("lines", [])
            if lines:
                longest = 0.0
                for line in lines:
                    if len(line) == 4:
                        x1, y1, x2, y2 = line
                        length = np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
                        longest = max(longest, length)
                info += f"Longest: {longest:.0f}px\n"
        else:
            info += "No shot detected"
        self.info_text.insert("1.0", info)
        self.info_text.config(state=tk.DISABLED)
    
    def _on_slider_change(self, value: str):
        try:
            frame_idx = int(float(value))
            self._load_and_display_frame(frame_idx)
        except ValueError:
            pass
    
    def _on_shot_selected(self, event):
        selection = self.shots_listbox.curselection()
        if selection:
            idx = selection[0]
            shot_frame = list(self.detected_shots.keys())[idx]
            self._load_and_display_frame(shot_frame)
    
    def _toggle_playback(self):
        if not self.video_path:
            messagebox.showwarning("Warning", "Please select a video first")
            return
        
        self.is_playing = not self.is_playing
        if self.is_playing:
            self._play_video_loop()
    
    def _play_video_loop(self):
        if not self.is_playing or not self.cap:
            return
        
        self._load_and_display_frame(self.current_frame_idx + 1)
        
        if self.current_frame_idx >= self.total_frames - 1:
            self.is_playing = False
            self.status_label.config(text="Status: Playback finished", fg="blue")
            return
        
        # Schedule next frame
        delay_ms = max(1, int(1000 / self.fps)) if self.fps > 0 else 33
        self.root.after(delay_ms, self._play_video_loop)
    
    async def _fetch_token_async(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.engine_url}/token/")
                response.raise_for_status()
                data = response.json()
                self.auth_token = data.get("token")
                return True
        except Exception as e:
            messagebox.showerror("Error", f"Failed to fetch token: {e}")
            return False
    
    async def _analyze_video_async(self):
        if not self.cap or not self.video_path:
            messagebox.showwarning("Warning", "No video loaded")
            return
        
        # Fetch token
        if not await self._fetch_token_async():
            return
        
        self.is_analyzing = True
        self.status_label.config(text="Status: Analyzing...", fg="orange")
        self.root.update()
        
        # Load all frames
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        self.frame_images = []
        for i in range(self.total_frames):
            ret, frame = self.cap.read()
            if ret:
                self.frame_images.append(frame)
            else:
                break
        
        # Analyze consecutive frame pairs
        async with httpx.AsyncClient(base_url=self.engine_url, timeout=30.0) as client:
            for i in range(len(self.frame_images) - 1):
                if not self.is_analyzing:
                    break
                
                prev_frame = self.frame_images[i]
                curr_frame = self.frame_images[i + 1]
                
                # Encode frames as base64 JPEG
                _, prev_jpeg = cv2.imencode(".jpg", prev_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                _, curr_jpeg = cv2.imencode(".jpg", curr_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                
                prev_b64 = base64.b64encode(prev_jpeg).decode()
                curr_b64 = base64.b64encode(curr_jpeg).decode()
                
                payload = {
                    "camera_id": "viewer",
                    "subscriptions": ["SHOT_FIRED"],
                    "previous_frame": {
                        "frame_id": i,
                        "timestamp": i / self.fps if self.fps > 0 else 0,
                        "image_data": prev_b64,
                    },
                    "current_frame": {
                        "frame_id": i + 1,
                        "timestamp": (i + 1) / self.fps if self.fps > 0 else 0,
                        "image_data": curr_b64,
                    },
                }
                
                try:
                    response = await client.post(
                        "/events/pending",
                        json=payload,
                        headers={"Authorization": f"Bearer {self.auth_token}"},
                    )
                    response.raise_for_status()
                    events = response.json()
                    
                    for event in events:
                        if event.get("event_type") == "SHOT_FIRED":
                            shot_frame = event.get("frame_id", i + 1)
                            confidence = event.get("confidence", 0.0)
                            raw_payload = event.get("raw_payload", {})
                            lines = raw_payload.get("lines", [])
                            
                            print(f"[DETECTION] Frame {shot_frame}: confidence={confidence:.1%}, lines={lines}")
                            
                            self.detected_shots[shot_frame] = {
                                "confidence": confidence,
                                "diff_area": raw_payload.get("diff_area", 0),
                                "diff_ratio": raw_payload.get("diff_ratio", 0),
                                "line_count": raw_payload.get("line_count", 0),
                                "lines": lines,
                            }
                except Exception as e:
                    print(f"Error analyzing frame pair {i}-{i+1}: {e}")
                
                # Update progress
                progress = int(100 * (i + 1) / (len(self.frame_images) - 1))
                self.status_label.config(text=f"Status: Analyzing... {progress}%", fg="orange")
                self.root.update()
        
        # Update shots listbox
        self._refresh_shots_list()
        
        self.is_analyzing = False
        self.status_label.config(text=f"Status: Analysis complete ({len(self.detected_shots)} shots found)", fg="green")
    
    def _start_analysis(self):
        if not self.video_path:
            messagebox.showwarning("Warning", "Please select a video first")
            return
        
        # Run async analysis in background thread
        thread = threading.Thread(target=self._run_analysis_thread, daemon=True)
        thread.start()
    
    def _run_analysis_thread(self):
        asyncio.run(self._analyze_video_async())
    
    def _refresh_shots_list(self):
        self.shots_listbox.delete(0, tk.END)
        for frame_idx in sorted(self.detected_shots.keys()):
            shot = self.detected_shots[frame_idx]
            confidence = shot.get("confidence", 0.0)
            time_sec = frame_idx / self.fps if self.fps > 0 else 0
            self.shots_listbox.insert(tk.END, f"Frame {frame_idx:4d} ({time_sec:6.2f}s) - {confidence:.0%}")
    
    def _reset(self):
        self.is_playing = False
        self.is_analyzing = False
        self.current_frame_idx = 0
        self.detected_shots.clear()
        self.frame_images.clear()
        if self.cap:
            self.cap.release()
            self.cap = None
        
        # Clear display
        self.canvas.config(image="")
        self.canvas.image = None
        self.info_text.config(state=tk.NORMAL)
        self.info_text.delete("1.0", tk.END)
        self.info_text.config(state=tk.DISABLED)
        self.shots_listbox.delete(0, tk.END)
        self.status_label.config(text="Status: Ready", fg="blue")


def main():
    root = tk.Tk()
    app = ShotDetectorViewer(root)
    root.mainloop()


if __name__ == "__main__":
    main()
