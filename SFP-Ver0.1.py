#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
SpineForge Planner
-----------------
A specialized application for spine surgeons to measure and analyze spine parameters
from DICOM and other medical images. This tool provides interactive measurement of 
key spinal and pelvic parameters including:
- CBVA (Chin-Brow Vertical Angle)
- C2-C7 Lordosis & SVA (Sagittal Vertical Axis)
- T1 Slope
- Lumbar Lordosis
- Sacral Slope
- Pelvic Tilt & Incidence
- SVA (Sagittal Vertical Axis)

The application allows for landmark placement, measurement calculation, and
export of results.
"""

# Increase recursion limit for complex operations
import sys
sys.setrecursionlimit(sys.getrecursionlimit() * 5)  # Increase recursion limit for complex operations

# Core UI and file handling imports
import tkinter as tk
from tkinter import filedialog, messagebox
import pydicom  # For DICOM medical image handling
import numpy as np
from PIL import Image, ImageTk, ImageEnhance  # Image processing
import math  # For trigonometric calculations
import pyperclip  # For clipboard operations
import ctypes  # For low-level Windows API access
from ctypes import wintypes  # Windows types for screenshot functionality

# Platform-specific imports for screenshot functionality
if sys.platform == "darwin":  # macOS
    try:
        import pyscreenshot as ImageGrab
    except ImportError:
        from PIL import ImageGrab
else:  # Windows/Linux
    from PIL import ImageGrab


class SpineForgePlanner:
    """
    Main application class for SpineForge Planner.
    
    This class handles the UI, image loading, landmark placement,
    measurement calculations, and display of spine parameters.
    """
    
    def __init__(self, root):
        """
        Initialize the SpineForge Planner application.
        
        Args:
            root: The tkinter root window
        """
        self.root = root
        self.root.title("SpineForge Planner")

        # -- UI SETUP --
        # Left sidebar for controls and measurements
        self.sidebar = tk.Frame(root, width=400, bg="lightgray")
        self.sidebar.pack(side="left", fill="y")

        # Top file action buttons
        file_frame = tk.Frame(self.sidebar, bg="lightgray")
        file_frame.pack(pady=5)
        self.load_button = tk.Button(file_frame, text="Load DICOM", command=self.load_dicom)
        self.load_button.pack(side="left", padx=2)
        self.save_button = tk.Button(file_frame, text="Save Screenshot", command=self.save_screenshot)
        self.save_button.pack(side="left", padx=2)
        self.copy_button = tk.Button(file_frame, text="Copy Results", command=self.copy_to_clipboard)
        self.copy_button.pack(side="left", padx=2)
        # transient status message
        self.status_label = tk.Label(self.sidebar, text="", bg="lightgray", fg="green", font=("Arial", 10))
        self.status_label.pack(pady=(5,0))

        # Contrast control slider
        contrast_frame = tk.Frame(self.sidebar, bg="lightgray")
        contrast_frame.pack(pady=5, fill="x")
        tk.Label(contrast_frame, text="Image Contrast:", bg="lightgray").pack(side="left", padx=5)
        self.contrast_slider = tk.Scale(contrast_frame, from_=0.5, to=3.0, resolution=0.1, 
                                       orient="horizontal", command=self.update_contrast)
        self.contrast_slider.set(1.0)  # Default contrast
        self.contrast_slider.pack(side="left", fill="x", expand=True, padx=5)
        
        # Toggle for draggable measurement labels
        toggle_frame = tk.Frame(self.sidebar, bg="lightgray")
        toggle_frame.pack(pady=5, fill="x")
        self.drag_labels_var = tk.BooleanVar(value=True)
        self.drag_labels_check = tk.Checkbutton(toggle_frame, text="Enable Draggable Labels", 
                                              variable=self.drag_labels_var, bg="lightgray")
        self.drag_labels_check.pack(side="left", padx=5)
        
        # Text size control for measurements
        text_size_frame = tk.Frame(self.sidebar, bg="lightgray")
        text_size_frame.pack(pady=5, fill="x")
        tk.Label(text_size_frame, text="Measurement Size:", bg="lightgray").pack(side="left", padx=5)
        self.text_size_slider = tk.Scale(text_size_frame, from_=8, to=16, resolution=1, 
                                        orient="horizontal", command=self.update_text_size)
        self.text_size_slider.set(12)  # Default text size
        self.text_size_slider.pack(side="left", fill="x", expand=True, padx=5)
        
        # Instructions for user
        instruction_frame = tk.Frame(self.sidebar, bg="lightgray")
        instruction_frame.pack(pady=5, fill="x")
        self.instruction_label = tk.Label(instruction_frame, 
                                        text="Right-click and drag to move labels", 
                                        bg="lightgray", fg="blue", font=("Arial", 9, "bold"))
        self.instruction_label.pack(padx=5)

        # -- LANDMARK SELECTION BUTTONS --
        # Create buttons for selecting anatomical landmarks to place
        button_frame = tk.Frame(self.sidebar, bg="lightgray")
        button_frame.pack(pady=5)
        self.point_buttons = [
            # (Display name, internal name)
            ("Brow", "brow"), ("Chin", "chin"),  # For CBVA measurement
            ("C2 Ant", "C2_ant"), ("C2 Post", "C2_post"),  # Cervical landmarks
            ("C7 Ant", "C7_ant"), ("C7 Post", "C7_post"),
            ("T1 Ant", "T1_ant"), ("T1 Post", "T1_post"),  # Thoracic landmarks
            ("L1 Ant", "L1_ant"), ("L1 Post", "L1_post"),  # Lumbar landmarks
            ("L5 Ant", "L5_ant"), ("L5 Post", "L5_post"),
            ("S1 Ant", "S1_ant"), ("S1 Post", "S1_post"),  # Sacral landmarks
            ("Femoral Head", "hip")  # For pelvic measurements
        ]
        # Arrange buttons in two columns
        for i in range(0, len(self.point_buttons), 2):
            row = tk.Frame(button_frame, bg="lightgray")
            row.pack()
            for j in range(2):
                if i + j < len(self.point_buttons):
                    label, name = self.point_buttons[i + j]
                    tk.Button(row, text=label, width=18, 
                             command=lambda n=name: self.set_current_landmark(n)).pack(side="left", padx=2, pady=1)

        # -- MEASUREMENT DISPLAY AREA --
        self.info_label = tk.Label(self.sidebar, text="Measurements:", bg="lightgray")
        self.info_label.pack(pady=5)
        self.measurement_labels = {}  # Dictionary to store measurement value widgets
        self.measurements_frame = tk.Frame(self.sidebar, bg="white")
        self.measurements_frame.pack(fill="x", padx=5, pady=5)
        # List of all measurements to display
        measurement_names = [
            "CBVA", "C2–C7 Lordosis", "C2–C7 SVA", "T1 Slope", "Lumbar Lordosis",
            "Sacral Slope", "Pelvic Tilt", "PI (vector)", "SVA"
        ]
        # Create label widgets for each measurement
        for name in measurement_names:
            row = tk.Frame(self.measurements_frame, bg="white")
            row.pack(fill="x", pady=1)
            label = tk.Label(row, text=f"{name}:", anchor="w", width=20, bg="white")
            label.pack(side="left")
            val_label = tk.Label(row, text="--", anchor="w", bg="white")
            val_label.pack(side="left")
            self.measurement_labels[name] = val_label  # Store reference to update later

        # -- MAIN IMAGE CANVAS --
        self.canvas = tk.Canvas(root, bg="black", cursor="cross")
        self.canvas.pack(fill="both", expand=True)

        # -- EVENT BINDINGS --
        # Image interaction
        self.canvas.bind("<Button-1>", self.on_click)  # Left click to place landmarks
        self.canvas.bind("<MouseWheel>", self.on_zoom)  # Mouse wheel for zoom
        # Support for Linux and Mac mouse wheel
        self.canvas.bind("<Button-4>", lambda e: self.on_zoom(e, delta=120))  # Scroll up
        self.canvas.bind("<Button-5>", lambda e: self.on_zoom(e, delta=-120))  # Scroll down
        self.canvas.bind("<B2-Motion>", self.on_pan)  # Middle button drag to pan
        self.canvas.bind("<ButtonPress-2>", self.start_pan)  # Start panning
        
        # Label dragging bindings
        self.canvas.bind("<B3-Motion>", self.on_drag_label)  # Right button drag to move labels
        self.canvas.bind("<ButtonPress-3>", self.start_drag_label)  # Start dragging label
        self.canvas.bind("<ButtonRelease-3>", self.stop_drag_label)  # Stop dragging label

        # -- STATE VARIABLES --
        self.image = None  # Current display image (with adjustments)
        self.original_image = None  # Original loaded image (unadjusted)
        self.tk_image = None  # Tkinter PhotoImage for display
        self.zoom = 0.1  # Initial zoom level (very zoomed out for overview)
        self.offset = [0, 0]  # Image offset for panning
        self.pan_start = [0, 0]  # Starting point for pan operation

        self.ds = None  # DICOM dataset
        self.pixel_spacing = [1.0, 1.0]  # Image pixel spacing [x, y] in mm
        self.landmarks = {}  # Dictionary to store landmark coordinates
        self.current_landmark_name = None  # Currently selected landmark to place
        self.text_size = 12  # Default size for measurement text
        self.landmark_label_size = 7  # Smaller size for landmark labels
        
        # Label dragging state
        self.dragging_label = None  # Currently dragged label
        self.drag_start = None  # Starting point for drag operation
        self.label_offsets = {}  # Custom positions for measurement labels
        self.label_anchor_points = {}  # Anchor points for measurement lines
        
        # Visual representation colors for different measurements
        self.colors = {
            "CBVA": "#FF5733",     # Orange-red
            "C2-C7": "#3498DB",    # Blue
            "T1": "#2ECC71",       # Green
            "Lumbar": "#9B59B6",   # Purple
            "Sacral": "#F1C40F",   # Yellow
            "Pelvic": "#E74C3C",   # Red
            "SVA": "#1ABC9C",      # Teal
            "femoral": "#D35400"   # Dark orange
        }

    def create_outlined_text(self, x, y, text, fill_color, font_size, tags):
        """
        Create text with white/black outline for better visibility on any background.
        
        Args:
            x, y: Text position coordinates
            text: Text string to display
            fill_color: Color of the main text
            font_size: Size of the text font
            tags: Canvas tags for the text items
            
        Returns:
            Tuple of (main_text_id, list_of_outline_ids)
        """
        # Create text shadow/outline using multiple offset positions
        offsets = [(-1,-1), (1,-1), (-1,1), (1,1)]
        outline_items = []
        
        # Create outlines first (they'll be behind the main text)
        for dx, dy in offsets:
            outline = self.canvas.create_text(
                x+dx, y+dy, 
                text=text, 
                fill='white' if fill_color != 'white' else 'black',  # Contrast with main text color
                font=('Arial', font_size, 'bold'),
                anchor="nw",
                tags=tags
            )
            outline_items.append(outline)
        
        # Create the main text on top
        text_item = self.canvas.create_text(
            x, y, text=text, 
            fill=fill_color, 
            font=('Arial', font_size, 'bold'),
            anchor="nw",
            tags=tags
        )
        
        return text_item, outline_items

    def update_text_size(self, val):
        """
        Update the text size for measurements and redraw.
        
        Args:
            val: New text size value from slider
        """
        self.text_size = int(val)
        if self.image is not None:
            self.display_image()  # Redraw with new text size
            
    def start_drag_label(self, event):
        """
        Begin dragging a measurement label when right mouse button is pressed.
        
        Args:
            event: Mouse event
        """
        if not self.drag_labels_var.get():  # Check if dragging is enabled
            return
            
        # Check if we're clicking on a text label
        closest = self.canvas.find_closest(event.x, event.y)
        if closest and len(closest) > 0:
            item_id = closest[0]
            tags = self.canvas.gettags(item_id)
            # Look for items with label: tag
            if tags and any(tag.startswith("label:") for tag in tags):
                # Extract label name from tag
                for tag in tags:
                    if tag.startswith("label:"):
                        label_name = tag.split(":", 1)[1]
                        self.dragging_label = label_name
                        self.drag_start = (event.x, event.y)
                        # Change cursor to indicate dragging
                        self.canvas.config(cursor="fleur")
                        return
    
    def on_drag_label(self, event):
        """
        Move a measurement label during dragging.
        
        Args:
            event: Mouse drag event
        """
        if not self.drag_labels_var.get() or not self.dragging_label or not self.drag_start:
            return
            
        # Calculate drag delta
        dx = event.x - self.drag_start[0]
        dy = event.y - self.drag_start[1]
        
        # Find all canvas items with this label's tag and move them
        for item in self.canvas.find_withtag(f"label:{self.dragging_label}"):
            self.canvas.move(item, dx, dy)
        
        # Update the stored label offset
        if self.dragging_label not in self.label_offsets:
            self.label_offsets[self.dragging_label] = [0, 0]
        
        self.label_offsets[self.dragging_label][0] += dx
        self.label_offsets[self.dragging_label][1] += dy
        
        # Redraw connecting lines between labels and anchor points
        self.draw_connecting_lines()
        
        # Update drag start point
        self.drag_start = (event.x, event.y)
    
    def draw_connecting_lines(self):
        """
        Draw dashed lines connecting measurement labels to their anchor points.
        This provides visual connection when labels are moved away from measurements.
        """
        # First, delete any existing connecting lines
        self.canvas.delete("connecting_line")
        
        # Now draw lines from each label to its anchor point
        for label_name, anchor_point in self.label_anchor_points.items():
            if label_name in self.label_offsets:  # Only draw for labels that have been moved
                # Find the label on canvas
                label_items = list(self.canvas.find_withtag(f"label:{label_name}"))
                if label_items:
                    # Get the label's background rectangle (should be the first item)
                    bg_item = None
                    for item in label_items:
                        if "bg" in self.canvas.gettags(item):
                            bg_item = item
                            break
                    
                    if bg_item:
                        # Get the center of the label's background
                        bbox = self.canvas.bbox(bg_item)
                        if bbox:
                            label_center_x = (bbox[0] + bbox[2]) / 2
                            label_center_y = (bbox[1] + bbox[3]) / 2
                            
                            # Draw a dashed line from the label to its anchor point
                            color = self.colors.get(label_name.split("_")[0], "#FFFFFF")  # Use the measurement's color
                            line = self.canvas.create_line(
                                label_center_x, label_center_y, 
                                anchor_point[0], anchor_point[1],
                                dash=(4, 4), width=1, fill=color, tags=("connecting_line",)
                            )
                            # Make sure the line is behind all other items
                            self.canvas.tag_raise(line, "image")
    
    def stop_drag_label(self, event):
        """
        End dragging of a measurement label.
        
        Args:
            event: Mouse release event
        """
        self.dragging_label = None
        self.drag_start = None
        # Reset cursor
        self.canvas.config(cursor="cross")

    def set_current_landmark(self, name):
        """
        Set the currently selected landmark to place on the image.
        
        Args:
            name: Internal name of the landmark
        """
        self.current_landmark_name = name
        # Update UI to show which landmark is currently being placed
        for label, btn_name in self.point_buttons:
            if btn_name == name:
                self.info_label.config(text=f"Click to place: {label}")
                return
                
    def load_dicom(self):
        """
        Load a DICOM file and display it on the canvas.
        Extracts pixel spacing information and resets measurements.
        """
        try:
            # Open file dialog to select DICOM file
            filepath = filedialog.askopenfilename(filetypes=[("DICOM files", "*.dcm")])
            if not filepath:
                return
                
            # Read DICOM dataset
            self.ds = pydicom.dcmread(filepath)
            
            # Convert pixel data to displayable image
            pixel_array = self.ds.pixel_array.astype(np.float32)
            norm_img = ((pixel_array - np.min(pixel_array)) / np.ptp(pixel_array) * 255).astype(np.uint8)
            self.original_image = Image.fromarray(norm_img)
            self.image = self.original_image
            
            # Extract pixel spacing for accurate measurements
            if hasattr(self.ds, 'PixelSpacing'):
                spacing = self.ds.PixelSpacing
                self.pixel_spacing = [float(spacing[0]), float(spacing[1])]
            else:
                self.pixel_spacing = [1.0, 1.0]
                messagebox.showwarning("Warning", "No pixel spacing found in DICOM. Using default values.")
            
            # Reset zoom and position for new image
            self.zoom = 0.1
            self.offset = [0, 0]
            
            # Clear existing landmarks and measurements
            self.landmarks = {}
            self.label_offsets = {}  # Clear label position offsets
            self.label_anchor_points = {}  # Clear anchor points
            self.update_measurements()
            
            # Display the image
            self.display_image()
            self.info_label.config(text="DICOM loaded successfully. Place landmarks.")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load DICOM file: {str(e)}")
    
    def update_contrast(self, val):
        """
        Update the contrast of the displayed image.
        
        Args:
            val: New contrast value from slider
        """
        if self.original_image is None:
            return
        enhancer = ImageEnhance.Contrast(self.original_image)
        self.image = enhancer.enhance(float(val))
        self.display_image()
    
    def copy_to_clipboard(self):
        """
        Copy all measurements to the clipboard as formatted text.
        """
        try:
            text = ""
            for name, label in self.measurement_labels.items():
                if label['text'] != "--":  # Only include non-empty measurements
                    text += f"{name}: {label['text']}\n"
            pyperclip.copy(text)
            self.status_label.config(text="Copied.")
            self.root.after(10_000, lambda: self.status_label.config(text=""))
        except Exception as e:
            messagebox.showerror("Error", f"Failed to copy to clipboard: {str(e)}")

    def display_image(self):
        """
        Display the current image on the canvas with appropriate zoom and position.
        Also draws all landmarks and measurements.
        """
        if self.image is None:
            return
        
        try:
            # Resize according to zoom level
            resized = self.image.resize((int(self.image.width * self.zoom), int(self.image.height * self.zoom)))
            self.tk_image = ImageTk.PhotoImage(resized)
            
            # Clear canvas and draw image
            self.canvas.delete("all")
            self.canvas.create_image(self.offset[0], self.offset[1],
                         anchor="nw", image=self.tk_image,
                         tags=("image",))
            
            # Draw landmarks and measurements
            self.draw_landmarks()
            self.draw_connecting_lines()  # Add connecting lines after drawing labels
        except Exception as e:
            messagebox.showerror("Error", f"Display error: {str(e)}")

    def on_click(self, event):
        """
        Handle left-click to place landmarks on the image.
        
        Args:
            event: Mouse click event
        """
        if not self.current_landmark_name or self.image is None:
            return
            
        # Convert from canvas coordinates to image coordinates
        x = int((event.x - self.offset[0]) / self.zoom)
        y = int((event.y - self.offset[1]) / self.zoom)
        
        # Check if coordinates are within image boundaries
        if 0 <= x < self.image.width and 0 <= y < self.image.height:
            self.landmarks[self.current_landmark_name] = (x, y)
            self.current_landmark_name = None
            self.info_label.config(text="Landmark placed. Select next landmark.")
            self.display_image()
            self.update_measurements()

    def draw_landmarks(self):
        """
        Draw all placed landmarks and associated measurements on the canvas.
        This includes visualization of various spine parameters.
        """
        # Helper function to convert image coordinates to canvas coordinates
        def scaled(pt):
            return pt[0] * self.zoom + self.offset[0], pt[1] * self.zoom + self.offset[1]
        
        # Helper function to get label position with any custom offset applied
        def get_label_position(base_pos, label_name):
            x, y = base_pos
            if label_name in self.label_offsets:
                x += self.label_offsets[label_name][0]
                y += self.label_offsets[label_name][1]
            return x, y
        
        # Helper function to store anchor points for measurement labels
        def store_anchor_point(label_name, anchor_point):
            self.label_anchor_points[label_name] = anchor_point
        
        # Draw each landmark point
        for name, (x, y) in self.landmarks.items():
            sx, sy = scaled((x, y))
            # Draw the landmark point
            self.canvas.create_oval(sx-4, sy-4, sx+4, sy+4, fill='red', outline='white', width=2)
            # Add small label near the landmark
            self.canvas.create_text(sx+5, sy-5, text=name, fill='yellow', anchor='nw', 
                                  font=('Arial', self.landmark_label_size, 'bold'))
        
        lm = self.landmarks
        px, py = self.pixel_spacing[1], self.pixel_spacing[0]
        
        # -- DRAW CBVA (CHIN-BROW VERTICAL ANGLE) --
        if all(k in lm for k in ["chin", "brow"]):
            brow_x, brow_y = scaled(lm["brow"])
            chin_x, chin_y = scaled(lm["chin"])
            self.canvas.create_line(brow_x, brow_y, chin_x, chin_y, fill=self.colors["CBVA"], width=2)
            # Calculate midpoint for displaying angle
            mid_x, mid_y = (brow_x + chin_x) / 2, (brow_y + chin_y) / 2
            angle = math.degrees(math.atan2((lm['brow'][0]-lm['chin'][0])*px, -(lm['brow'][1]-lm['chin'][1])*py))
            
            # Store midpoint as anchor for the label
            store_anchor_point("CBVA", (mid_x, mid_y))
            
            # Position label with any custom offset
            label_x, label_y = get_label_position((mid_x + 15, mid_y), "CBVA")
            # Add semi-transparent background for better readability
            bg = self.canvas.create_rectangle(
                label_x - 5, label_y - 5, 
                label_x + 120, label_y + 20, 
                fill='black', outline='white', width=1, stipple='gray50', 
                tags=("label:CBVA", "bg")
            )
            
            # Create outlined text
            self.create_outlined_text(
                label_x, label_y, 
                text=f"CBVA: {angle:.1f}°", 
                fill_color=self.colors["CBVA"],
                font_size=self.text_size,
                tags=("label:CBVA",)
            )
        
        # -- DRAW C2-C7 MEASUREMENTS --
        if all(k in lm for k in ["C2_ant", "C2_post", "C7_ant", "C7_post"]):
            c2a_x, c2a_y = scaled(lm["C2_ant"])
            c2p_x, c2p_y = scaled(lm["C2_post"])
            c7a_x, c7a_y = scaled(lm["C7_ant"])
            c7p_x, c7p_y = scaled(lm["C7_post"])
            
            # Draw C2 endplate
            self.canvas.create_line(c2a_x, c2a_y, c2p_x, c2p_y, fill=self.colors["C2-C7"], width=2)
            # Draw C7 endplate
            self.canvas.create_line(c7a_x, c7a_y, c7p_x, c7p_y, fill=self.colors["C2-C7"], width=2)
            # Connect C2 post to C7 post for SVA
            self.canvas.create_line(c2p_x, c2p_y, c7p_x, c2p_y, fill=self.colors["C2-C7"], width=1, dash=(4, 2))
            self.canvas.create_line(c7p_x, c2p_y, c7p_x, c7p_y, fill=self.colors["C2-C7"], width=1, dash=(4, 2))
            
            # Display C2-C7 lordosis
            c2 = self.calculate_angle(lm["C2_ant"], lm["C2_post"])
            c7 = self.calculate_angle(lm["C7_ant"], lm["C7_post"])
            lordosis = abs(c2 - c7)
            
            # Store midpoint as anchor for lordosis label
            lordosis_anchor = ((c2p_x + c7p_x) / 2, (c2p_y + c7p_y) / 2)
            store_anchor_point("C2-C7Lordosis", lordosis_anchor)
            
            # Position C2-C7 Lordosis label with any custom offset
            label_x, label_y = get_label_position((lordosis_anchor[0] + 15, lordosis_anchor[1]), "C2-C7Lordosis")
            # Add background
            bg = self.canvas.create_rectangle(
                label_x - 5, label_y - 5, 
                label_x + 180, label_y + 20, 
                fill='black', outline='white', width=1, stipple='gray50', 
                tags=("label:C2-C7Lordosis", "bg")
            )
            
            # Create outlined text
            self.create_outlined_text(
                label_x, label_y, 
                text=f"C2-C7 Lordosis: {lordosis:.1f}°",
                fill_color=self.colors["C2-C7"],
                font_size=self.text_size,
                tags=("label:C2-C7Lordosis",)
            )
            
            # Store anchor point for SVA label
            sva_anchor = (c7p_x, c2p_y)
            store_anchor_point("C2-C7SVA", sva_anchor)
            
            # Position C2-C7 SVA label
            sva = abs((lm['C2_post'][0] - lm['C7_post'][0]) * px)
            label_x, label_y = get_label_position((c7p_x + 15, c2p_y - 20), "C2-C7SVA")
            # Add background
            bg = self.canvas.create_rectangle(
                label_x - 5, label_y - 5, 
                label_x + 150, label_y + 20, 
                fill='black', outline='white', width=1, stipple='gray50', 
                tags=("label:C2-C7SVA", "bg")
            )
            
            # Create outlined text
            self.create_outlined_text(
                label_x, label_y, 
                text=f"C2-C7 SVA: {sva:.1f}mm",
                fill_color=self.colors["C2-C7"],
                font_size=self.text_size,
                tags=("label:C2-C7SVA",)
            )
        
        # Create outlined text (white/black outline with colored fill for better visibility)
            self.create_outlined_text(
                label_x, label_y, 
                text=f"C2-C7 SVA: {sva:.1f}mm",  # Display the sagittal vertical axis measurement
                fill_color=self.colors["C2-C7"],  # Use consistent color scheme for C2-C7 measurements
                font_size=self.text_size,  # Use current user-adjustable text size
                tags=("label:C2-C7SVA",)  # Tag for identifying this label for dragging/updating
            )
        
        # -- DRAW T1 SLOPE --
        if all(k in lm for k in ["T1_ant", "T1_post"]):
            # Get canvas coordinates of T1 anterior and posterior points
            t1a_x, t1a_y = scaled(lm["T1_ant"])
            t1p_x, t1p_y = scaled(lm["T1_post"])
            
            # Draw T1 endplate line
            self.canvas.create_line(t1a_x, t1a_y, t1p_x, t1p_y, fill=self.colors["T1"], width=2)
            
            # Draw horizontal reference line for angle measurement
            self.canvas.create_line(t1a_x, t1a_y, t1p_x, t1a_y, fill=self.colors["T1"], width=1, dash=(4, 2))
            
            # Calculate T1 slope (angle between endplate and horizontal)
            t1_slope = self.calculate_angle(lm["T1_ant"], lm["T1_post"])
            
            # Store T1 midpoint as anchor for label
            t1_anchor = ((t1a_x + t1p_x)/2, t1a_y - 20)  # Position above T1 endplate
            store_anchor_point("T1Slope", t1_anchor)
            
            # Position T1 slope label, applying any custom offset
            label_x, label_y = get_label_position(t1_anchor, "T1Slope")
            
            # Add semi-transparent background for better readability
            bg = self.canvas.create_rectangle(
                label_x - 5, label_y - 5, 
                label_x + 120, label_y + 20, 
                fill='black', outline='white', width=1, stipple='gray50', 
                tags=("label:T1Slope", "bg")
            )
            
            # Create outlined text with measurement value
            self.create_outlined_text(
                label_x, label_y, 
                text=f"T1 Slope: {t1_slope:.1f}°",  # Display T1 slope in degrees
                fill_color=self.colors["T1"],  # Use consistent color scheme for T1
                font_size=self.text_size,  # Use current user-adjustable text size
                tags=("label:T1Slope",)  # Tag for identifying this label
            )
        
        # -- DRAW LUMBAR LORDOSIS (L1-L5) --
        if all(k in lm for k in ["L1_ant", "L1_post", "L5_ant", "L5_post"]):
            # Get canvas coordinates of L1 and L5 vertebrae
            l1a_x, l1a_y = scaled(lm["L1_ant"])
            l1p_x, l1p_y = scaled(lm["L1_post"])
            l5a_x, l5a_y = scaled(lm["L5_ant"])
            l5p_x, l5p_y = scaled(lm["L5_post"])
            
            # Draw L1 endplate
            self.canvas.create_line(l1a_x, l1a_y, l1p_x, l1p_y, fill=self.colors["Lumbar"], width=2)
            
            # Draw L5 endplate
            self.canvas.create_line(l5a_x, l5a_y, l5p_x, l5p_y, fill=self.colors["Lumbar"], width=2)
            
            # Connect anterior points and posterior points with dotted lines to visualize lordosis
            self.canvas.create_line(l1a_x, l1a_y, l5a_x, l5a_y, fill=self.colors["Lumbar"], width=1, dash=(5, 3))
            self.canvas.create_line(l1p_x, l1p_y, l5p_x, l5p_y, fill=self.colors["Lumbar"], width=1, dash=(5, 3))
            
            # Calculate lordosis angle
            l1_angle = self.calculate_angle(lm["L1_ant"], lm["L1_post"])
            l5_angle = self.calculate_angle(lm["L5_ant"], lm["L5_post"])
            ll = abs(l1_angle - l5_angle)  # Lordosis is the difference between endplate angles
            
            # Store midpoint as anchor for lordosis label (offset to left of spine)
            ll_anchor = ((l1a_x + l5a_x)/2 - 25, (l1a_y + l5a_y)/2)
            store_anchor_point("LumbarLordosis", ll_anchor)
            
            # Position Lumbar Lordosis label, applying any custom offset
            label_x, label_y = get_label_position(ll_anchor, "LumbarLordosis") 
            
            # Add semi-transparent background for better readability
            bg = self.canvas.create_rectangle(
                label_x - 5, label_y - 5, 
                label_x + 180, label_y + 20, 
                fill='black', outline='white', width=1, stipple='gray50', 
                tags=("label:LumbarLordosis", "bg")
            )
            
            # Create outlined text with measurement value
            self.create_outlined_text(
                label_x, label_y, 
                text=f"Lumbar Lordosis: {ll:.1f}°",  # Display lordosis in degrees
                fill_color=self.colors["Lumbar"],  # Use consistent color scheme for lumbar
                font_size=self.text_size,  # Use current user-adjustable text size
                tags=("label:LumbarLordosis",)  # Tag for identifying this label
            )
        
        # -- DRAW SACRAL SLOPE --
        if all(k in lm for k in ["S1_ant", "S1_post"]):
            # Get canvas coordinates of S1 endplate
            s1a_x, s1a_y = scaled(lm["S1_ant"])
            s1p_x, s1p_y = scaled(lm["S1_post"])
            
            # Draw S1 endplate line
            self.canvas.create_line(s1a_x, s1a_y, s1p_x, s1p_y, fill=self.colors["Sacral"], width=2)
            
            # Draw horizontal reference line for angle measurement
            self.canvas.create_line(s1a_x, s1a_y, s1p_x + 40, s1a_y, fill=self.colors["Sacral"], width=1, dash=(4, 2))
            
            # Calculate sacral slope (angle between S1 endplate and horizontal)
            s1_slope = self.calculate_angle(lm["S1_ant"], lm["S1_post"])
            
            # Store position as anchor for sacral slope label
            s1_anchor = (s1p_x + 20, s1a_y - 15)  # Position to right of S1 endplate
            store_anchor_point("SacralSlope", s1_anchor)
            
            # Position Sacral Slope label, applying any custom offset
            label_x, label_y = get_label_position(s1_anchor, "SacralSlope")
            
            # Add semi-transparent background for better readability
            bg = self.canvas.create_rectangle(
                label_x - 5, label_y - 5, 
                label_x + 150, label_y + 20, 
                fill='black', outline='white', width=1, stipple='gray50', 
                tags=("label:SacralSlope", "bg")
            )
            
            # Create outlined text with measurement value
            self.create_outlined_text(
                label_x, label_y, 
                text=f"Sacral Slope: {s1_slope:.1f}°",  # Display sacral slope in degrees
                fill_color=self.colors["Sacral"],  # Use consistent color scheme for sacral
                font_size=self.text_size,  # Use current user-adjustable text size
                tags=("label:SacralSlope",)  # Tag for identifying this label
            )
        
        # -- DRAW PELVIC TILT AND PELVIC INCIDENCE --
        if all(k in lm for k in ["S1_ant", "S1_post", "hip"]):
            # Get canvas coordinates of S1 endplate and femoral head
            s1a_x, s1a_y = scaled(lm["S1_ant"])
            s1p_x, s1p_y = scaled(lm["S1_post"])
            hip_x, hip_y = scaled(lm["hip"])
            
            # Calculate midpoint of sacral endplate
            s1_mid_x = (s1a_x + s1p_x) / 2
            s1_mid_y = (s1a_y + s1p_y) / 2
            
            # Draw line from hip to sacral midpoint (for pelvic parameters)
            self.canvas.create_line(hip_x, hip_y, s1_mid_x, s1_mid_y, fill=self.colors["Pelvic"], width=2)
            
            # Draw vertical reference line for pelvic tilt measurement
            self.canvas.create_line(hip_x, hip_y, hip_x, s1_mid_y, fill=self.colors["Pelvic"], width=1, dash=(4, 2))
            
            # Calculate pelvic parameters from landmark coordinates
            sa, sp, hip = lm['S1_ant'], lm['S1_post'], lm['hip']
            mid = ((sa[0] + sp[0]) / 2, (sa[1] + sp[1]) / 2)  # S1 endplate midpoint
            
            # Vector from hip to midpoint, accounting for pixel spacing
            dx, dy = (mid[0] - hip[0]) * px, (mid[1] - hip[1]) * py
            
            # Calculate pelvic tilt (angle between vertical and hip-to-midpoint line)
            pt = abs(math.degrees(math.atan2(dx, -dy)))
            
            # Calculate pelvic incidence using vector method
            # Step 1: Create vector from hip to sacral midpoint
            vec1 = np.array([dx, dy])
            
            # Step 2: Create vector along sacral endplate
            vec_s1 = np.array([(sp[0] - sa[0]) * px, (sp[1] - sa[1]) * py])
            
            # Step 3: Create vector perpendicular to sacral endplate
            vec2 = np.array([-vec_s1[1], vec_s1[0]])
            
            # Step 4: Calculate angle between vectors using dot product formula
            # cos(θ) = (v1·v2)/(|v1|·|v2|)
            cos_a = np.clip(np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2)), -1.0, 1.0)
            pi_v = math.degrees(math.acos(cos_a))
            pi_v = min(pi_v, 180 - pi_v)  # Take smaller angle (acute/right)
            
            # Calculate midpoint for PT label position
            pt_x, pt_y = (hip_x + s1_mid_x) / 2, (hip_y + s1_mid_y) / 2
            
            # Store PT anchor point for dragging
            store_anchor_point("PelvicTilt", (pt_x, pt_y))
            
            # Position PT label, applying any custom offset
            label_x, label_y = get_label_position((pt_x + 20, pt_y), "PelvicTilt")
            
            # Add semi-transparent background for better readability
            bg = self.canvas.create_rectangle(
                label_x - 5, label_y - 5, 
                label_x + 130, label_y + 20, 
                fill='black', outline='white', width=1, stipple='gray50', 
                tags=("label:PelvicTilt", "bg")
            )
            
            # Create outlined text with PT measurement
            self.create_outlined_text(
                label_x, label_y, 
                text=f"Pelvic Tilt: {pt:.1f}°",  # Display pelvic tilt in degrees
                fill_color=self.colors["Pelvic"],  # Use consistent color scheme for pelvic
                font_size=self.text_size,  # Use current user-adjustable text size
                tags=("label:PelvicTilt",)  # Tag for identifying this label
            )
            
            # Store PI anchor point (slightly below PT)
            store_anchor_point("PelvicIncidence", (pt_x, pt_y + 25))
            
            # Position PI label, applying any custom offset
            label_x, label_y = get_label_position((pt_x + 20, pt_y + 25), "PelvicIncidence")
            
            # Add semi-transparent background for better readability
            bg = self.canvas.create_rectangle(
                label_x - 5, label_y - 5, 
                label_x + 180, label_y + 20, 
                fill='black', outline='white', width=1, stipple='gray50', 
                tags=("label:PelvicIncidence", "bg")
            )
            
            # Create outlined text with PI measurement
            self.create_outlined_text(
                label_x, label_y, 
                text=f"Pelvic Incidence: {pi_v:.1f}°",  # Display pelvic incidence in degrees
                fill_color=self.colors["Pelvic"],  # Use consistent color scheme for pelvic
                font_size=self.text_size,  # Use current user-adjustable text size
                tags=("label:PelvicIncidence",)  # Tag for identifying this label
            )
        
        # -- DRAW SVA (SAGITTAL VERTICAL AXIS) --
        if all(k in lm for k in ["C7_post", "S1_post"]):
            # Get canvas coordinates of C7 and S1 posterior landmarks
            c7p_x, c7p_y = scaled(lm["C7_post"])
            s1p_x, s1p_y = scaled(lm["S1_post"])
            
            # Draw C7 plumbline (vertical line from C7)
            self.canvas.create_line(c7p_x, c7p_y, c7p_x, s1p_y, fill=self.colors["SVA"], width=2, dash=(5, 3))
            
            # Draw horizontal line from plumbline to S1 posterior
            self.canvas.create_line(c7p_x, s1p_y, s1p_x, s1p_y, fill=self.colors["SVA"], width=2)
            
            # Calculate SVA (horizontal distance from C7 plumbline to S1 posterior)
            sva = abs((lm['C7_post'][0] - lm['S1_post'][0]) * px)  # Convert to mm using pixel spacing
            
            # Store SVA anchor point for dragging
            sva_anchor = ((c7p_x + s1p_x) / 2, s1p_y + 20)  # Position below horizontal line
            store_anchor_point("SVA", sva_anchor)
            
            # Position SVA label, applying any custom offset
            label_x, label_y = get_label_position(sva_anchor, "SVA")
            
            # Add semi-transparent background for better readability
            bg = self.canvas.create_rectangle(
                label_x - 5, label_y - 5, 
                label_x + 120, label_y + 20, 
                fill='black', outline='white', width=1, stipple='gray50', 
                tags=("label:SVA", "bg")
            )
            
            # Create outlined text with SVA measurement
            self.create_outlined_text(
                label_x, label_y, 
                text=f"SVA: {sva:.1f}mm",  # Display SVA in millimeters
                fill_color=self.colors["SVA"],  # Use consistent color scheme for SVA
                font_size=self.text_size,  # Use current user-adjustable text size
                tags=("label:SVA",)  # Tag for identifying this label
            )
            
    def calculate_angle(self, p1, p2):
        """
        Calculate the angle between a line and the horizontal axis.
        
        This method calculates the angle formed by a line (defined by two points)
        and the horizontal axis, taking into account the pixel spacing for accurate
        measurements in real-world units.
        
        Args:
            p1: First point (anterior point) as (x, y) tuple in image coordinates
            p2: Second point (posterior point) as (x, y) tuple in image coordinates
            
        Returns:
            float: Angle in degrees, positive for upward slope, negative for downward slope
        """
        # Calculate differences in x and y, accounting for pixel spacing
        # Pixel spacing converts from pixel units to millimeters
        dx = (p2[0] - p1[0]) * self.pixel_spacing[1]  # X difference in mm
        dy = (p2[1] - p1[1]) * self.pixel_spacing[0]  # Y difference in mm
        
        # Use atan2 to find angle with horizontal
        # Note: We negate dy because image coordinates increase downward,
        # opposite to the mathematical convention where y increases upward
        return math.degrees(math.atan2(-dy, dx))

    def update_measurements(self):
        """
        Update all measurement values in the sidebar display.
        
        This method calculates all spine parameters based on the current landmark
        positions and updates the display labels in the sidebar. It gets called
        whenever landmarks are placed or updated.
        """
        lm = self.landmarks  # Shorthand for landmarks dictionary
        px, py = self.pixel_spacing[1], self.pixel_spacing[0]  # Pixel spacing (mm/pixel)
        
        # Helper function to update a specific measurement label
        def update(name, val):
            """Update a measurement label with a new value if it exists"""
            if name in self.measurement_labels:
                self.measurement_labels[name]["text"] = val

        # -- Update CBVA (Chin-Brow Vertical Angle) --
        if all(k in lm for k in ["chin", "brow"]):
            # Calculate angle between vertical and chin-brow line
            # CBVA indicates the head position/gaze direction
            cbva = math.degrees(math.atan2((lm['brow'][0]-lm['chin'][0])*px, -(lm['brow'][1]-lm['chin'][1])*py))
            update("CBVA", f"{cbva:.2f}°")
        else:
            update("CBVA", "--")  # No measurement if landmarks missing
        
        # -- Update C2-C7 Lordosis --
        if all(k in lm for k in ["C2_ant", "C2_post", "C7_ant", "C7_post"]):
            # Calculate angles of C2 and C7 endplates relative to horizontal
            c2 = self.calculate_angle(lm["C2_ant"], lm["C2_post"])
            c7 = self.calculate_angle(lm["C7_ant"], lm["C7_post"])
            # C2-C7 lordosis is the absolute difference between these angles
            # This measures the curvature of the cervical spine
            update("C2–C7 Lordosis", f"{abs(c2 - c7):.2f}°")
        else:
            update("C2–C7 Lordosis", "--")  # No measurement if landmarks missing
        
        # -- Update C2-C7 SVA (Sagittal Vertical Axis) --    
        if all(k in lm for k in ["C2_post", "C7_post"]):
            # Horizontal distance between C2 and C7 posterior landmarks, converted to mm
            # This measures cervical spine alignment in the sagittal plane
            c2c7_sva = abs((lm['C2_post'][0] - lm['C7_post'][0]) * px)
            update("C2–C7 SVA", f"{c2c7_sva:.2f} mm")
        else:
            update("C2–C7 SVA", "--")  # No measurement if landmarks missing
        
        # -- Update T1 Slope --
        if all(k in lm for k in ["T1_ant", "T1_post"]):
            # Angle of T1 superior endplate relative to horizontal
            # T1 slope is critical for evaluating cervical alignment
            t1_slope = self.calculate_angle(lm['T1_ant'], lm['T1_post'])
            update("T1 Slope", f"{t1_slope:.2f}°") 
        else:
            update("T1 Slope", "--")  # No measurement if landmarks missing
        
        # -- Update Lumbar Lordosis (L1-L5) --
        if all(k in lm for k in ["L1_ant", "L1_post", "L5_ant", "L5_post"]):
            # Calculate angles of L1 and L5 endplates relative to horizontal
            l1 = self.calculate_angle(lm["L1_ant"], lm["L1_post"])
            l5 = self.calculate_angle(lm["L5_ant"], lm["L5_post"])
            # Lumbar lordosis is the absolute difference between these angles
            # This measures the curvature of the lumbar spine
            update("Lumbar Lordosis", f"{abs(l1 - l5):.2f}°")
        else:
            update("Lumbar Lordosis", "--")  # No measurement if landmarks missing
        
        # -- Update Sacral Slope --    
        if all(k in lm for k in ["S1_ant", "S1_post"]):
            # Angle of S1 endplate relative to horizontal
            # Sacral slope affects lumbopelvic alignment
            s1_slope = self.calculate_angle(lm['S1_ant'], lm['S1_post'])
            update("Sacral Slope", f"{s1_slope:.2f}°")
        else:
            update("Sacral Slope", "--")  # No measurement if landmarks missing
        
        # -- Update Pelvic Parameters --
        if all(k in lm for k in ["S1_ant", "S1_post", "hip"]):
            # Extract landmark coordinates
            sa, sp, hip = lm['S1_ant'], lm['S1_post'], lm['hip']
            # Calculate midpoint of sacral endplate
            mid = ((sa[0] + sp[0]) / 2, (sa[1] + sp[1]) / 2)
            # Vector from hip to sacral midpoint
            dx, dy = (mid[0] - hip[0]) * px, (mid[1] - hip[1]) * py
            
            # Calculate Pelvic Tilt (angle between vertical and hip-midpoint line)
            # PT represents pelvic rotation around the femoral head axis
            pt = abs(math.degrees(math.atan2(dx, -dy)))
            update("Pelvic Tilt", f"{pt:.2f}°")
            
            # Calculate Pelvic Incidence using vector method
            # PI is a morphological parameter that doesn't change with position
            vec1 = np.array([dx, dy])  # Hip to sacral midpoint vector
            vec_s1 = np.array([(sp[0] - sa[0]) * px, (sp[1] - sa[1]) * py])  # Sacral endplate vector
            vec2 = np.array([-vec_s1[1], vec_s1[0]])  # Perpendicular to sacral endplate
            
            # Calculate angle between vectors using dot product
            cos_a = np.clip(np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2)), -1.0, 1.0)
            pi_v = math.degrees(math.acos(cos_a))
            pi_v = min(pi_v, 180 - pi_v)  # Take smaller angle (acute/right)
            update("PI (vector)", f"{pi_v:.2f}°")
            
            # Note: PI (sum PT+SS) calculation removed as requested
        else:
            update("Pelvic Tilt", "--")  # No measurement if landmarks missing
            update("PI (vector)", "--")  # No measurement if landmarks missing
        
        # -- Update SVA (Sagittal Vertical Axis) --    
        if all(k in lm for k in ["C7_post", "S1_post"]):
            # Horizontal distance between C7 and S1 posterior landmarks, converted to mm
            # SVA is a key measure of global sagittal balance
            sva = abs((lm['C7_post'][0] - lm['S1_post'][0]) * px)
            update("SVA", f"{sva:.2f} mm")
        else:
            update("SVA", "--")  # No measurement if landmarks missing

    def _grab_canvas_via_gdi(self):
        """
        Capture the canvas client area via Windows GDI for high-quality screenshots.
        
        This method uses the Windows GDI (Graphics Device Interface) to capture
        the canvas contents directly from video memory, which provides higher quality
        and more accurate results than normal screenshot methods. It handles DPI
        scaling properly and captures exactly what is visible on screen.
        
        Returns:
            PIL.Image: The captured canvas image in RGB format, ready for saving
        """
        # Constants for Windows GDI operations
        SRCCOPY = 0x00CC0020  # Copy source rectangle directly to destination rectangle

        # Step 1: Get canvas HWND (window handle) and dimensions
        hwnd = self.canvas.winfo_id()  # Get window handle of canvas
        rect = wintypes.RECT()  # Structure to receive window dimensions
        ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(rect))
        width = rect.right - rect.left
        height = rect.bottom - rect.top

        # Step 2: Get device contexts (DCs) for drawing operations
        hdc = ctypes.windll.user32.GetDC(hwnd)  # Get device context of canvas
        hdc_mem = ctypes.windll.gdi32.CreateCompatibleDC(hdc)  # Create memory DC
        hbmp = ctypes.windll.gdi32.CreateCompatibleBitmap(hdc, width, height)  # Create bitmap
        ctypes.windll.gdi32.SelectObject(hdc_mem, hbmp)  # Select bitmap into memory DC

        # Step 3: Copy canvas contents to memory DC
        ctypes.windll.gdi32.BitBlt(
            hdc_mem, 0, 0, width, height,  # Destination: memory DC
            hdc, 0, 0, SRCCOPY  # Source: canvas DC, using direct copy
        )

        # Step 4: Prepare BITMAPINFO structure for a 32-bit BGRA image
        class BITMAPINFOHEADER(ctypes.Structure):
            """Structure containing information about the dimensions and color format of a DIB"""
            _fields_ = [
                ("biSize", wintypes.DWORD),
                ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD),
            ]
            
        class BITMAPINFO(ctypes.Structure):
            """Structure containing bitmap header info and color table"""
            _fields_ = [
                ("bmiHeader", BITMAPINFOHEADER),
                ("bmiColors", wintypes.DWORD * 3),  # Color table
            ]

        # Initialize and fill bitmap info header
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = width
        bmi.bmiHeader.biHeight = -height  # Negative = top-down DIB with origin at upper left
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32  # 32 bits per pixel (BGRA)
        bmi.bmiHeader.biCompression = 0  # BI_RGB = no compression

        # Step 5: Allocate buffer and retrieve the bitmap bits
        buf_len = width * height * 4  # 4 bytes per pixel (BGRA)
        buffer = (ctypes.c_byte * buf_len)()
        ctypes.windll.gdi32.GetDIBits(
            hdc_mem, hbmp,  # DC and bitmap to get bits from
            0, height,  # Start scan line and number of scan lines
            buffer,  # Buffer to receive bits
            ctypes.byref(bmi),  # Bitmap info
            0  # DIB_RGB_COLORS (color table contains RGB values)
        )

        # Step 6: Convert to PIL image (from BGRA to RGB format)
        raw_bytes = bytes(buffer)
        img = Image.frombytes(
            "RGB",  # Output mode
            (width, height),  # Image size
            raw_bytes,  # Pixel data
            "raw",  # Raw decoder
            "BGRX"  # Source format (BGRA but ignore alpha channel)
        )

        # Step 7: Clean up GDI resources to prevent memory leaks
        ctypes.windll.gdi32.DeleteObject(hbmp)
        ctypes.windll.gdi32.DeleteDC(hdc_mem)
        ctypes.windll.user32.ReleaseDC(hwnd, hdc)

        return img

    def save_screenshot(self):
        """
        Capture and save a high-quality screenshot of the canvas contents.
        
        This method:
        1. Captures the canvas using low-level Windows GDI for high quality
        2. Automatically crops to include only the relevant content
        3. Scales up and saves with high DPI for printing/publication quality
        
        The saved image includes all measurements and visual aids,
        making it suitable for clinical documentation or research.
        """
        if self.image is None:
            messagebox.showinfo("Info", "No image loaded to save.")
            return

        # Step 1: Ensure all drawing operations are complete
        self.canvas.update_idletasks()

        # Step 2: Capture the canvas using platform-specific method
        shot = self._grab_canvas_via_gdi()

        # Step 3: Find the bounding box of everything on the canvas
        bbox = self.canvas.bbox("all")  # Returns (x0,y0,x1,y1) in Tkinter coordinates
        if bbox:
            x0_l, y0_l, x1_l, y1_l = bbox

            # Add margin around the content for visual appeal
            MARGIN_LOGICAL = 5  # Small margin in logical pixels

            # Account for display scaling (high DPI displays)
            try:
                scale = float(self.root.tk.call("tk", "scaling"))
            except Exception:
                scale = 1.0

            # Convert logical coordinates to physical pixels
            x0 = max(0, int((x0_l - MARGIN_LOGICAL) * scale))
            y0 = max(0, int((y0_l - MARGIN_LOGICAL) * scale))
            x1 = min(shot.width, int((x1_l + MARGIN_LOGICAL) * scale))
            y1 = min(shot.height, int((y1_l + MARGIN_LOGICAL) * scale))

            # Crop the screenshot to include only the relevant content
            shot = shot.crop((x0, y0, x1, y1))

        # Step 4: Save the screenshot to a user-selected location
        try:
            path = filedialog.asksaveasfilename(
                title="Save canvas snapshot",
                defaultextension=".png",
                filetypes=[("PNG image", "*.png")])
            
            if path:
                # Double the resolution for high-quality output suitable for publications
                shot = shot.resize((shot.width*2, shot.height*2), Image.LANCZOS)
                shot.save(path, dpi=(600, 600))  # Save with high DPI for printing
                self.status_label.config(text="Saved.")
                self.root.after(10_000, lambda: self.status_label.config(text=""))
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save screenshot:\n{e}")

    def on_zoom(self, event, delta=None):
        """
        Handle zoom in/out events from mouse wheel.
        
        This method implements smooth zooming centered on the cursor position,
        which provides a more intuitive zoom experience compared to center-based
        zooming.
        
        Args:
            event: Mouse wheel event containing position information
            delta: Optional scroll amount (for Linux/Mac compatibility)
        """
        if delta is None:  # Windows uses delta in event
            delta = event.delta
            
        # Store previous zoom for calculating offset adjustment
        old_zoom = self.zoom
        
        # Adjust zoom factor (1.1x for zoom in, 0.9x for zoom out)
        factor = 1.1 if delta > 0 else 0.9
        self.zoom *= factor
        
        # Get cursor position relative to canvas
        cx, cy = event.x, event.y
        
        # Adjust offset to zoom toward/away from cursor position
        # This makes the point under the cursor stay fixed during zoom
        # Formula: new_offset = cursor - (cursor - old_offset) * (new_zoom / old_zoom)
        self.offset[0] = cx - (cx - self.offset[0]) * (self.zoom / old_zoom)
        self.offset[1] = cy - (cy - self.offset[1]) * (self.zoom / old_zoom)
        
        # Update display with new zoom level
        self.display_image()

    def start_pan(self, event):
        """
        Start panning operation when middle mouse button is pressed.
        
        Args:
            event: Mouse button press event containing position information
        """
        # Store initial position for calculating pan offset
        self.pan_start = [event.x, event.y]

    def on_pan(self, event):
        """
        Handle panning (middle mouse drag) to move the image.
        
        This method enables the user to navigate large images by
        dragging with the middle mouse button.
        
        Args:
            event: Mouse drag event containing position information
        """
        # Calculate movement since last position
        dx = event.x - self.pan_start[0]
        dy = event.y - self.pan_start[1]
        
        # Update offset for image position
        self.offset[0] += dx
        self.offset[1] += dy
        
        # Store current position for next movement calculation
        self.pan_start = [event.x, event.y]
        
        # Update display with new position
        self.display_image()

if __name__ == "__main__":
    """
    Main entry point for SpineForge Planner application.
    
    This block initializes the Tkinter root window and creates an instance
    of the SpineForgePlanner application, then starts the event loop.
    """
    root = tk.Tk()
    root.geometry("1200x800")  # Set initial window size
    app = SpineForgePlanner(root)  # Create application instance
    root.mainloop()  # Start the Tkinter event loop