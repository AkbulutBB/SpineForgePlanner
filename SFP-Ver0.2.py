# -*- coding: utf-8 -*-
"""
SpineForge Planner - Ver 0.2
-----------------
A specialized application for spine surgeons to measure and analyze spine parameters
from DICOM and other medical images. This tool provides interactive measurement of 
key spinal and pelvic parameters and surgical planning.

"""

import sys
sys.setrecursionlimit(sys.getrecursionlimit() * 5)

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import pydicom
import numpy as np
from PIL import Image, ImageTk, ImageEnhance
import math
import pyperclip
import ctypes
from ctypes import wintypes
import os
from stl import mesh
from scipy.interpolate import splprep, splev
import sys
import time

# Platform-specific imports for screenshot functionality
if sys.platform == "darwin":  # macOS
    try:
        import pyscreenshot as ImageGrab
    except ImportError:
        from PIL import ImageGrab
else:  # Windows/Linux
    from PIL import ImageGrab

class SpineForgePlanner:
    def __init__(self, root):
        self.root = root
        self.root.title("SpineForge Planner")
        
        # Initialize core state before UI creation
        self.image = None
        self.original_image = None
        self.tk_image = None
        self.zoom = 0.1  # start very zoomed out for better overview
        self.offset = [0, 0]
        self.pan_start = [0, 0]

        self.ds = None
        self.pixel_spacing = [1.0, 1.0]
        self.landmarks = {}
        self.current_landmark_name = None
        self.text_size = 12  # Default measurement text size
        self.landmark_label_size = 7  # Smaller size for landmark labels
        
        # Label dragging state
        self.dragging_label = None
        self.drag_start = None
        self.label_offsets = {}  # To store custom positions for measurement labels
        self.label_anchor_points = {}  # To store anchor points for measurement lines
        
        # Visual representation colors for different measurements
        self.colors = {
            "CBVA": "#FF5733",  # Orange-red
            "C2-C7": "#3498DB",  # Blue
            "T1": "#2ECC71",     # Green
            "Lumbar": "#9B59B6", # Purple
            "Sacral": "#F1C40F", # Yellow
            "Pelvic": "#E74C3C", # Red
            "SVA": "#1ABC9C",    # Teal
            "femoral": "#D35400" # Dark orange
        }
        
        # Implant state
        self.screws = []
        self.current_screw = None
        self.cages = []
        
        # Rod state
        self.rod_points = []
        self.rod_line = None
        self.rod_model = None
        
        # Create a main frame that will contain all UI elements
        self.main_frame = tk.Frame(root)
        self.main_frame.pack(fill="both", expand=True)
        
        # Now create the UI elements with the new layout
        # Left sidebar for tools
        self.sidebar = tk.Frame(self.main_frame, width=400, bg="lightgray")
        self.sidebar.pack(side="left", fill="y")
    
        # Create the status label
        self.status_label = tk.Label(self.sidebar, text="", bg="lightgray", fg="green", font=("Arial", 10))
        self.status_label.pack(pady=(5,0))

        # Top row for file actions
        file_frame = tk.Frame(self.sidebar, bg="lightgray")
        file_frame.pack(pady=5)
        self.load_button = tk.Button(file_frame, text="Load DICOM", command=self.load_dicom)
        self.load_button.pack(side="left", padx=2)
        self.save_button = tk.Button(file_frame, text="Save Screenshot", command=self.save_screenshot)
        self.save_button.pack(side="left", padx=2)
        self.copy_button = tk.Button(file_frame, text="Copy Results", command=self.copy_to_clipboard)
        self.copy_button.pack(side="left", padx=2)

        # Add contrast control
        contrast_frame = tk.Frame(self.sidebar, bg="lightgray")
        contrast_frame.pack(pady=5, fill="x")
        tk.Label(contrast_frame, text="Image Contrast:", bg="lightgray").pack(side="left", padx=5)
        self.contrast_slider = tk.Scale(contrast_frame, from_=0.5, to=3.0, resolution=0.1, 
                                       orient="horizontal", command=self.update_contrast)
        self.contrast_slider.set(1.0)
        self.contrast_slider.pack(side="left", fill="x", expand=True, padx=5)
        
        # Add toggle for draggable labels
        toggle_frame = tk.Frame(self.sidebar, bg="lightgray")
        toggle_frame.pack(pady=5, fill="x")
        self.drag_labels_var = tk.BooleanVar(value=True)
        self.drag_labels_check = tk.Checkbutton(toggle_frame, text="Enable Draggable Labels", 
                                              variable=self.drag_labels_var, bg="lightgray")
        self.drag_labels_check.pack(side="left", padx=5)
        
        # Text size control
        text_size_frame = tk.Frame(self.sidebar, bg="lightgray")
        text_size_frame.pack(pady=5, fill="x")
        tk.Label(text_size_frame, text="Measurement Size:", bg="lightgray").pack(side="left", padx=5)
        self.text_size_slider = tk.Scale(text_size_frame, from_=8, to=16, resolution=1, 
                                        orient="horizontal", command=self.update_text_size)
        self.text_size_slider.set(12)  # Default text size
        self.text_size_slider.pack(side="left", fill="x", expand=True, padx=5)
        
        # Add instruction label
        instruction_frame = tk.Frame(self.sidebar, bg="lightgray")
        instruction_frame.pack(pady=5, fill="x")
        self.instruction_label = tk.Label(instruction_frame, 
                                        text="Right-click and drag to move labels", 
                                        bg="lightgray", fg="blue", font=("Arial", 9, "bold"))
        self.instruction_label.pack(padx=5)

        # Tab control for different tool panels
        self.tab_control = ttk.Notebook(self.sidebar)
        self.tab_control.pack(fill="both", expand=True, pady=5)
        
        # Landmark Tab
        self.landmark_tab = tk.Frame(self.tab_control, bg="lightgray")
        self.tab_control.add(self.landmark_tab, text="Landmarks")

        # Implant Tab
        self.implant_tab = tk.Frame(self.tab_control, bg="lightgray")
        self.tab_control.add(self.implant_tab, text="Implants")
        
        # Rod Export Tab
        self.rod_tab = tk.Frame(self.tab_control, bg="lightgray")
        self.tab_control.add(self.rod_tab, text="Rod Export")

        # Landmark buttons in two columns
        button_frame = tk.Frame(self.landmark_tab, bg="lightgray")
        button_frame.pack(pady=5)
        self.point_buttons = [
            ("Brow", "brow"), ("Chin", "chin"),
            ("C2 Ant", "C2_ant"), ("C2 Post", "C2_post"),
            ("C7 Ant", "C7_ant"), ("C7 Post", "C7_post"),
            ("T1 Ant", "T1_ant"), ("T1 Post", "T1_post"),
            ("L1 Ant", "L1_ant"), ("L1 Post", "L1_post"),
            ("L5 Ant", "L5_ant"), ("L5 Post", "L5_post"),
            ("S1 Ant", "S1_ant"), ("S1 Post", "S1_post"),
            ("Left Femoral Head Edge 1", "LFH_edge1"), ("Left Femoral Head Edge 2", "LFH_edge2"),
            ("Right Femoral Head Edge 1", "RFH_edge1"), ("Right Femoral Head Edge 2", "RFH_edge2")
        ]
        for i in range(0, len(self.point_buttons), 2):
            row = tk.Frame(button_frame, bg="lightgray")
            row.pack()
            for j in range(2):
                if i + j < len(self.point_buttons):
                    label, name = self.point_buttons[i + j]
                    tk.Button(row, text=label, width=18, command=lambda n=name: self.set_current_landmark(n)).pack(side="left", padx=2, pady=1)

        
        # Implant options
        implant_frame = tk.Frame(self.implant_tab, bg="lightgray")
        implant_frame.pack(pady=5, fill="x")
        
        tk.Label(implant_frame, text="Implant Type:", bg="lightgray").pack(anchor="w", padx=5)
        
        self.implant_type = tk.StringVar(value="screw")
        tk.Radiobutton(implant_frame, text="Pedicle Screw", variable=self.implant_type, value="screw", bg="lightgray", command=self.update_implant_options).pack(anchor="w", padx=20)
        tk.Radiobutton(implant_frame, text="Cage/Spacer", variable=self.implant_type, value="cage", bg="lightgray", command=self.update_implant_options).pack(anchor="w", padx=20)
        
        # Vertebral Level Selection - common for both screws and cages
        tk.Label(implant_frame, text="Vertebral Level:", bg="lightgray").pack(anchor="w", padx=5, pady=(10,0))
        level_frame = tk.Frame(implant_frame, bg="lightgray")
        level_frame.pack(fill="x", padx=5, pady=2)
        
        self.level_var = tk.StringVar(value="L3")
        self.level_dropdown = ttk.Combobox(level_frame, textvariable=self.level_var)
        self.level_dropdown['values'] = ('T4', 'T5', 'T6', 'T7', 'T8', 'T9', 'T10', 'T11', 'T12', 'L1', 'L2', 'L3', 'L4', 'L5', 'S1')
        self.level_dropdown.pack(side="left", fill="x", expand=True)
        
        # Frame for screw parameters
        self.screw_params_frame = tk.Frame(implant_frame, bg="lightgray")
        self.screw_params_frame.pack(fill="x", padx=5, pady=5)
        
        tk.Label(self.screw_params_frame, text="Screw Parameters:", bg="lightgray").pack(anchor="w", pady=(5,0))
        
        screw_options_frame = tk.Frame(self.screw_params_frame, bg="lightgray")
        screw_options_frame.pack(fill="x", padx=5, pady=5)
        
        tk.Label(screw_options_frame, text="Diameter (mm):", bg="lightgray").grid(row=0, column=0, sticky="w")
        self.screw_diameter = tk.StringVar(value="6.5")
        diameter_entry = ttk.Combobox(screw_options_frame, textvariable=self.screw_diameter, width=5)
        diameter_entry['values'] = ('4.5', '5.0', '5.5', '6.0', '6.5', '7.0', '7.5', '8.0')
        diameter_entry.grid(row=0, column=1, padx=5, pady=2)
        
        tk.Label(screw_options_frame, text="Length (mm):", bg="lightgray").grid(row=1, column=0, sticky="w")
        self.screw_length = tk.StringVar(value="45")
        length_entry = ttk.Combobox(screw_options_frame, textvariable=self.screw_length, width=5)
        length_entry['values'] = ('30', '35', '40', '45', '50', '55', '60')
        length_entry.grid(row=1, column=1, padx=5, pady=2)
        
        self.place_screw_button = tk.Button(self.screw_params_frame, text="Place Screw", command=self.place_screw)
        self.place_screw_button.pack(pady=5)
        
        self.cage_points = []
        
        # Frame for cage parameters
        self.cage_params_frame = tk.Frame(implant_frame, bg="lightgray")
        self.cage_params_frame.pack(fill="x", padx=5, pady=5)
        self.cage_params_frame.pack_forget()  # Initially hidden
        
        tk.Label(self.cage_params_frame, text="Cage Parameters:", bg="lightgray").pack(anchor="w", pady=(5,0))
        
        cage_options_frame = tk.Frame(self.cage_params_frame, bg="lightgray")
        cage_options_frame.pack(fill="x", padx=5, pady=5)
        
        tk.Label(cage_options_frame, text="Width (mm):", bg="lightgray").grid(row=0, column=0, sticky="w")
        self.cage_width = tk.StringVar(value="12")
        cage_width_entry = ttk.Combobox(cage_options_frame, textvariable=self.cage_width, width=5)
        cage_width_entry['values'] = ('8', '9', '10', '11', '12', '13', '14')
        cage_width_entry.grid(row=0, column=1, padx=5, pady=2)
        
        tk.Label(cage_options_frame, text="Length (mm):", bg="lightgray").grid(row=1, column=0, sticky="w")
        self.cage_length = tk.StringVar(value="28")
        cage_length_entry = ttk.Combobox(cage_options_frame, textvariable=self.cage_length, width=5)
        cage_length_entry['values'] = ('22', '24', '26', '28', '30', '32')
        cage_length_entry.grid(row=1, column=1, padx=5, pady=2)
        
        tk.Label(cage_options_frame, text="Height (mm):", bg="lightgray").grid(row=2, column=0, sticky="w")
        self.cage_height = tk.StringVar(value="10")
        cage_height_entry = ttk.Combobox(cage_options_frame, textvariable=self.cage_height, width=5)
        cage_height_entry['values'] = ('8', '9', '10', '11', '12', '13', '14')
        cage_height_entry.grid(row=2, column=1, padx=5, pady=2)
        
        tk.Label(cage_options_frame, text="Lordosis (°):", bg="lightgray").grid(row=3, column=0, sticky="w")
        self.cage_lordosis = tk.StringVar(value="6")
        cage_lordosis_entry = ttk.Combobox(cage_options_frame, textvariable=self.cage_lordosis, width=5)
        cage_lordosis_entry['values'] = ('0', '4', '6', '8', '10', '12', '15')
        cage_lordosis_entry.grid(row=3, column=1, padx=5, pady=2)
        
        self.place_cage_button = tk.Button(self.cage_params_frame, text="Place Cage", command=self.place_cage)
        self.place_cage_button.pack(pady=5)
        
        # Rod Export Options
        rod_frame = tk.Frame(self.rod_tab, bg="lightgray")
        rod_frame.pack(pady=5, fill="x")
        
        tk.Label(rod_frame, text="Rod Parameters:", bg="lightgray").pack(anchor="w", padx=5)
        
        param_frame = tk.Frame(rod_frame, bg="lightgray")
        param_frame.pack(fill="x", padx=5, pady=5)
        
        tk.Label(param_frame, text="Diameter (mm):", bg="lightgray").grid(row=0, column=0, sticky="w")
        self.rod_diameter = tk.StringVar(value="5.5")
        rod_diameter_entry = ttk.Combobox(param_frame, textvariable=self.rod_diameter, width=5)
        rod_diameter_entry['values'] = ('4.5', '5.0', '5.5', '6.0', '6.5')
        rod_diameter_entry.grid(row=0, column=1, padx=5, pady=2)
        
        tk.Label(param_frame, text="Side:", bg="lightgray").grid(row=1, column=0, sticky="w")
        self.rod_side = tk.StringVar(value="Both")
        rod_side_entry = ttk.Combobox(param_frame, textvariable=self.rod_side, width=5)
        rod_side_entry['values'] = ('Left', 'Right', 'Both')
        rod_side_entry.grid(row=1, column=1, padx=5, pady=2)
        
        self.generate_rod_button = tk.Button(rod_frame, text="Generate Rod Model", command=self.generate_rod_model)
        self.generate_rod_button.pack(pady=5)
        
        self.export_stl_button = tk.Button(rod_frame, text="Export as STL", command=self.export_rod_as_stl)
        self.export_stl_button.pack(pady=5)
        
        # Center panel for the image
        self.center_panel = tk.Frame(self.main_frame)
        self.center_panel.pack(side="left", fill="both", expand=True)
        
        # Canvas to show image
        self.canvas = tk.Canvas(self.center_panel, bg="black", cursor="cross")
        self.canvas.pack(fill="both", expand=True)
        
        # Right sidebar for measurements and results and status
        self.right_sidebar = tk.Frame(self.main_frame, width=350, bg="lightgray")
        self.right_sidebar.pack(side="right", fill="y")
        
        self.setup_status_area()
        
        # Add measurements header
        self.info_label = tk.Label(self.right_sidebar, text="Measurements:", bg="lightgray")
        self.info_label.pack(pady=5)
        
        # Create a frame to hold the scrollable area for measurements
        measurements_container = tk.Frame(self.right_sidebar, bg="white")
        measurements_container.pack(fill="x", padx=5, pady=5, expand=True)
        
        # Add scrollbar
        scrollbar = tk.Scrollbar(measurements_container)
        scrollbar.pack(side="right", fill="y")
        
        # Create a canvas that will be scrollable
        measurements_canvas = tk.Canvas(measurements_container, bg="white", 
                                      yscrollcommand=scrollbar.set,
                                      highlightthickness=0)
        measurements_canvas.pack(side="left", fill="both", expand=True)
        
        # Configure the scrollbar to scroll the canvas
        scrollbar.config(command=measurements_canvas.yview)
        
        # Create a frame inside the canvas to hold all the measurements
        self.measurements_frame = tk.Frame(measurements_canvas, bg="white")
        self.measurements_frame.bind("<Configure>", 
                                    lambda e: measurements_canvas.configure(
                                        scrollregion=measurements_canvas.bbox("all")))
        
        # Create a window inside the canvas to hold the frame
        measurements_canvas.create_window((0, 0), window=self.measurements_frame, 
                                        anchor="nw", width=measurements_canvas.winfo_width())
        
        # Respond to canvas resizing
        def on_canvas_resize(event):
            canvas_width = event.width
            measurements_canvas.itemconfig(measurements_canvas.find_all()[0], width=canvas_width)
            
        measurements_canvas.bind("<Configure>", on_canvas_resize)
        
        # Mouse wheel scrolling
        def _on_mousewheel(event):
            widget = event.widget
            if widget == measurements_canvas:
                measurements_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
                
        measurements_canvas.bind("<MouseWheel>", _on_mousewheel)
        
        # Add measurements
        measurement_names = [
            "CBVA", "C2–C7 Lordosis", "C2–C7 SVA", "T1 Slope", "Lumbar Lordosis",
            "Sacral Slope", "Pelvic Tilt", "PI (vector)", "SVA"
        ]
        
        self.measurement_labels = {}
        for name in measurement_names:
            row = tk.Frame(self.measurements_frame, bg="white")
            row.pack(fill="x", pady=1)
            label = tk.Label(row, text=f"{name}:", anchor="w", width=20, bg="white")
            label.pack(side="left")
            val_label = tk.Label(row, text="--", anchor="w", bg="white")
            val_label.pack(side="left")
            self.measurement_labels[name] = val_label
        
        # Implant summary section
        self.implant_summary_label = tk.Label(self.right_sidebar, text="Implants:", bg="lightgray")
        self.implant_summary_label.pack(pady=(20,5))
        
        # Frame for implant list
        self.implant_list_frame = tk.Frame(self.right_sidebar, bg="white")
        self.implant_list_frame.pack(fill="x", padx=5, pady=5)
        
        # Need to update for full scrollable height
        def _update_scroll_region(event=None):
            measurements_canvas.update_idletasks()  # Make sure everything is measured correctly
            measurements_canvas.configure(scrollregion=measurements_canvas.bbox("all"))
        
        self.root.after(100, _update_scroll_region)  # Update after window fully loads
    
        # Wait for all components to be created before setting up event bindings
        self.root.update()

        # Now set up the event bindings
        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<MouseWheel>", self.on_zoom)
        # Support for Linux and Mac which use <Button-4> and <Button-5> instead of MouseWheel
        self.canvas.bind("<Button-4>", lambda e: self.on_zoom(e, delta=120))
        self.canvas.bind("<Button-5>", lambda e: self.on_zoom(e, delta=-120))
        self.canvas.bind("<B2-Motion>", self.on_pan)
        self.canvas.bind("<ButtonPress-2>", self.start_pan)
        
        # Bindings for dragging text labels
        self.canvas.bind("<B3-Motion>", self.on_drag_label)
        self.canvas.bind("<ButtonPress-3>", self.start_drag_label)
        self.canvas.bind("<ButtonRelease-3>", self.stop_drag_label)
        
        # Set initial instruction
        self.info_label.config(text="Load a DICOM image to begin")

    def update_implant_options(self):
        """Show/hide appropriate parameter frames based on selected implant type"""
        implant_type = self.implant_type.get()
        
        if implant_type == "screw":
            self.screw_params_frame.pack(fill="x", padx=5, pady=5)
            self.cage_params_frame.pack_forget()
        else:  # cage
            self.screw_params_frame.pack_forget()
            self.cage_params_frame.pack(fill="x", padx=5, pady=5)

    def place_cage(self):
        """Begin placing a cage/spacer on the image"""
        self.current_screw = "placing_cage"
        self.osteotomy_points = []
        level = self.level_var.get()
        self.show_status(
            f"Click 4 points to define the cage at {level} level:\n"
            f"1) Left corner of inferior endplate\n"
            f"2) Right corner of inferior endplate\n"
            f"3) Left corner of superior endplate\n"
            f"4) Right corner of superior endplate",
            "info"
        )

    def create_outlined_text(self, x, y, text, fill_color, font_size, tags):
        """Create text with white/black outline for better visibility on any background"""
        # Create text shadow/outline using multiple offsets
        offsets = [(-1,-1), (1,-1), (-1,1), (1,1)]
        outline_items = []
        
        # Create outlines first (they'll be behind the main text)
        for dx, dy in offsets:
            outline = self.canvas.create_text(
                x+dx, y+dy, 
                text=text, 
                fill='white' if fill_color != 'white' else 'black',
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
        self.text_size = int(val)
        if self.image is not None:
            self.display_image()  # Redraw with new text size
            
    def start_drag_label(self, event):
        if not self.drag_labels_var.get():
            return
            
        # Check if we're clicking on a text label
        closest = self.canvas.find_closest(event.x, event.y)
        if closest and len(closest) > 0:
            item_id = closest[0]
            tags = self.canvas.gettags(item_id)
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
        if not self.drag_labels_var.get() or not self.dragging_label or not self.drag_start:
            return
            
        dx = event.x - self.drag_start[0]
        dy = event.y - self.drag_start[1]
        
        # Find all canvas items with this label's tag and move them
        for item in self.canvas.find_withtag(f"label:{self.dragging_label}"):
            self.canvas.move(item, dx, dy)
        
        # Update the label offset
        if self.dragging_label not in self.label_offsets:
            self.label_offsets[self.dragging_label] = [0, 0]
        
        self.label_offsets[self.dragging_label][0] += dx
        self.label_offsets[self.dragging_label][1] += dy
        
        # Redraw the connecting line to the anchor point
        self.draw_connecting_lines()
        
        self.drag_start = (event.x, event.y)
    
    def draw_connecting_lines(self):
        """Draw dashed lines connecting measurement labels to their anchor points"""
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
                            self.canvas.tag_lower(line)
    
    def stop_drag_label(self, event):
        self.dragging_label = None
        self.drag_start = None
        # Reset cursor
        self.canvas.config(cursor="cross")

    def set_current_landmark(self, name):
        self.current_landmark_name = name
        # Update UI to show which landmark is currently being placed
        for label, btn_name in self.point_buttons:
            if btn_name == name:
                self.info_label.config(text=f"Click to place: {label}")
                return
                
    def load_dicom(self):
        try:
            filepath = filedialog.askopenfilename(filetypes=[("DICOM files", "*.dcm")])
            if not filepath:
                return
                
            self.ds = pydicom.dcmread(filepath)
            pixel_array = self.ds.pixel_array.astype(np.float32)
            norm_img = ((pixel_array - np.min(pixel_array)) / np.ptp(pixel_array) * 255).astype(np.uint8)
            self.original_image = Image.fromarray(norm_img)
            self.image = self.original_image
            
            # Extract pixel spacing
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
            
            self.display_image()
            self.info_label.config(text="DICOM loaded successfully. Place landmarks.")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load DICOM file: {str(e)}")
    
    def update_contrast(self, val):
        if self.original_image is None:
            return
        enhancer = ImageEnhance.Contrast(self.original_image)
        self.image = enhancer.enhance(float(val))
        self.display_image()
        
    def copy_to_clipboard(self):
        try:
            text = ""
            for name, label in self.measurement_labels.items():
                if label['text'] != "--":
                    text += f"{name}: {label['text']}\n"
                        
            pyperclip.copy(text)
            self.show_status("Measurements copied to clipboard.", "success")
        except Exception as e:
            self.show_status(f"Failed to copy to clipboard: {str(e)}", "error")
   
    def display_image(self):
        if self.image is None:
            return
        # Make sure implant summary is up to date
        if hasattr(self, 'implant_list_frame'):
            self.update_implant_summary()
        
        try:
            resized = self.image.resize((int(self.image.width * self.zoom), int(self.image.height * self.zoom)))
            self.tk_image = ImageTk.PhotoImage(resized)
            self.canvas.delete("all")
            self.canvas.create_image(self.offset[0], self.offset[1], anchor="nw", image=self.tk_image)
            self.draw_landmarks()
            self.draw_implants()
            if self.rod_line:
                self.draw_rod()
            self.draw_connecting_lines()  # Add connecting lines after drawing labels
        except Exception as e:
            messagebox.showerror("Error", f"Display error: {str(e)}")

    def on_click(self, event):
        if self.current_landmark_name:
            # Convert from canvas coordinates to image coordinates
            x = int((event.x - self.offset[0]) / self.zoom)
            y = int((event.y - self.offset[1]) / self.zoom)
            
            # Check if coordinates are within image boundaries
            if self.image and 0 <= x < self.image.width and 0 <= y < self.image.height:
                self.landmarks[self.current_landmark_name] = (x, y)
                
                # Special handling for femoral head landmarks
                if self.current_landmark_name in ["LFH_edge1", "LFH_edge2", "RFH_edge1", "RFH_edge2"]:
                    # If this is the second point of a femoral head, draw a preview circle
                    if (self.current_landmark_name == "LFH_edge2" and "LFH_edge1" in self.landmarks):
                        p1 = self.landmarks["LFH_edge1"]
                        p2 = (x, y)
                        self.show_status(f"Left femoral head circle defined!", "success")
                    elif (self.current_landmark_name == "RFH_edge2" and "RFH_edge1" in self.landmarks):
                        p1 = self.landmarks["RFH_edge1"]
                        p2 = (x, y)
                        self.show_status(f"Right femoral head circle defined!", "success")
                
                self.current_landmark_name = None
                self.info_label.config(text="Landmark placed. Select next landmark.")
                self.display_image()
                self.update_measurements()
                
        
            
        elif self.current_screw == "placing_cage":
            x = int((event.x - self.offset[0]) / self.zoom)
            y = int((event.y - self.offset[1]) / self.zoom)
            
            self.cage_points.append((x, y))
            self.display_image()
            
            # Once we have 4 points for the cage
            if len(self.cage_points) == 4:
                width = float(self.cage_width.get())
                length = float(self.cage_length.get())
                height = float(self.cage_height.get())
                lordosis = float(self.cage_lordosis.get())
                level = self.level_var.get()
                
                self.cages.append({
                    "corners": self.osteotomy_points.copy(),
                    "width": width,
                    "length": length,
                    "height": height,
                    "lordosis": lordosis,
                    "level": level
                })
                
                self.cage_points = []
                self.current_screw = None
                self.show_status(
                    f"Cage placed at {level} - {width}×{length}×{height}mm with {lordosis}° lordosis", "success")

                self.display_image()
                
                # Update implant summary
                self.update_implant_summary()
                
        elif self.current_screw == "placing":
            x = int((event.x - self.offset[0]) / self.zoom)
            y = int((event.y - self.offset[1]) / self.zoom)
            
            # First click for screw head
            if len(self.osteotomy_points) == 0:
                self.osteotomy_points.append((x, y))
                self.display_image()
            else:
                # Second click for screw tip
                head_x, head_y = self.osteotomy_points[0]
                tip_x, tip_y = x, y
                
                # Calculate screw length in mm
                length = math.sqrt((tip_x - head_x)**2 + (tip_y - head_y)**2) * self.pixel_spacing[0]
                length = round(length)  # Round to nearest mm
                diameter = float(self.screw_diameter.get())
                
                self.screws.append({
                    "head": (head_x, head_y),
                    "tip": (tip_x, tip_y),
                    "diameter": diameter,
                    "length": length,
                    "level": self.level_var.get()
                })
                
                self.osteotomy_points = []
                self.current_screw = None
                
                self.end_persistent_instruction()
                
                self.show_status(
                    f"Screw placed at {self.level_var.get()} - Ø{diameter}mm x {length}mm", "success")

                self.display_image()
                
                self.update_implant_summary()
                
    def setup_status_area(self):
        """Set up the status notification area in the UI"""
        # Create a fixed-height frame for status messages at the top of the right sidebar
        self.status_area = tk.Frame(self.right_sidebar, bg="#333333", height=60)
        self.status_area.pack(fill="x", side="top", padx=5, pady=5)
        
        # Set width and propagate properties to maintain consistent size
        self.status_area.pack_propagate(False)  # Prevent size changes based on content
        
        # Status message label with larger font
        self.status_message = tk.Label(self.status_area, text="", font=("Arial", 12, "bold"), 
                                      bg="#333333", fg="#FFFFFF", wraplength=320, justify="left")
        self.status_message.pack(fill="x", padx=10, pady=10)
        
        # Add a small log area that shows recent messages
        self.log_frame = tk.Frame(self.status_area, bg="#333333")
        self.log_frame.pack(fill="x", padx=5)
        
        # Create 3 labels for recent messages (we'll rotate through them)
        self.log_labels = []
        for i in range(3):
            label = tk.Label(self.log_frame, text="", font=("Arial", 8), 
                           bg="#333333", fg="#AAAAAA", anchor="w")
            label.pack(fill="x", padx=5, pady=1)
            self.log_labels.append(label)
        
        # Message queue for the log
        self.message_queue = []
        
        # Keep track of persistent instructions
        self.persistent_instruction = False
        self.clear_timer = None

    def show_status(self, message, message_type="info", duration=5000, persistent=False):
        """
        Display a status message in the fixed status area without affecting the rest of the UI
        
        Args:
            message: The message to display
            message_type: 'info', 'error', 'success'
            duration: How long to display the message prominently (ms)
            persistent: If True, message stays until explicitly cleared or procedure complete
        """
        # Cancel any pending clear operation
        if hasattr(self, 'clear_timer') and self.clear_timer is not None:
            self.root.after_cancel(self.clear_timer)
            self.clear_timer = None
        
        # Define colors for different message types
        colors = {
            "info": {"bg": "#2980B9", "fg": "#FFFFFF"},    # Blue
            "error": {"bg": "#E74C3C", "fg": "#FFFFFF"},   # Red
            "success": {"bg": "#27AE60", "fg": "#FFFFFF"}, # Green
            "instruction": {"bg": "#8E44AD", "fg": "#FFFFFF"}  # Purple for instructions
        }
        
        # Use instruction type for persistent messages
        if persistent:
            message_type = "instruction"
            self.persistent_instruction = True
        
        # Get colors for this message type
        bg_color = colors.get(message_type, colors["info"])["bg"]
        fg_color = colors.get(message_type, colors["info"])["fg"]
        
        # Only update the status message content and colors
        self.status_message.config(text=message, bg=bg_color, fg=fg_color)
        self.status_area.config(bg=bg_color)
        
        # Add message to log queue
        timestamp = time.strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.message_queue.insert(0, log_entry)
        
        # Keep only the 3 most recent messages
        self.message_queue = self.message_queue[:3]
        
        # Update log labels without affecting layout
        for i, label in enumerate(self.log_labels):
            if i < len(self.message_queue):
                label.config(text=self.message_queue[i])
            else:
                label.config(text="")
        
        # Flash the status area to draw attention (only visual change, no layout)
        def flash_status(count=2, interval=500):
            if count > 0:
                current_bg = self.status_message.cget("bg")
                new_bg = "#FFFFFF" if current_bg != "#FFFFFF" else bg_color
                # Only change colors, not structure
                self.status_message.config(bg=new_bg)
                self.root.after(interval, lambda: flash_status(count-1, interval))
            else:
                # Reset to normal after flashing
                self.status_message.config(bg=bg_color)
                
                # Schedule clearing the prominent message after duration ONLY if not persistent
                if not persistent:
                    self.clear_timer = self.root.after(duration, self.clear_status)
        
        # Start flashing only if not already showing an error and not a persistent message
        if (message_type != "error" or not hasattr(self, '_showing_error')) and not persistent:
            flash_status()
    
    def clear_status(self):
        """Clear the prominent status message but keep the log"""
        # Only clear if not in the middle of a persistent instruction
        if not self.persistent_instruction:
            self.status_message.config(text="", bg="#333333")
            self.status_area.config(bg="#333333")
            if hasattr(self, 'clear_timer'):
                self.clear_timer = None
    
    def end_persistent_instruction(self):
        """Call this when a user completes a procedure requiring instructions"""
        self.persistent_instruction = False
        self.clear_status()

    def update_implant_summary(self):
        """Update the implant summary list in the right sidebar"""
        # Clear existing items
        for widget in self.implant_list_frame.winfo_children():
            widget.destroy()
        
        # Order vertebral levels from cranial to caudal
        def vertebral_level_order(level_str):
            if not level_str:
                return 999  # Put empty levels at the end
            
            # Extract the prefix and number
            if level_str.startswith('C'):
                prefix_value = 0
            elif level_str.startswith('T'):
                prefix_value = 100
            elif level_str.startswith('L'):
                prefix_value = 200
            elif level_str.startswith('S'):
                prefix_value = 300
            else:
                return 999  # Unknown prefix
            
            # Extract the numeric part
            try:
                number = int(''.join(filter(str.isdigit, level_str)))
                return prefix_value + number
            except ValueError:
                return prefix_value + 99  # No numeric part
        
        # Configure scrollable frame
        canvas = tk.Canvas(self.implant_list_frame, bg="white")
        scrollbar = tk.Scrollbar(self.implant_list_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg="white")
        
        # Bind scrollable frame to canvas
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Pack scrollbar and canvas
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Add screws to summary, sorted by vertebral level
        if self.screws:
            tk.Label(scrollable_frame, text="Screws:", bg="white", font=("Arial", 9, "bold")).pack(anchor="w")
            
            # Sort screws from cranial to caudal
            sorted_screws = sorted(enumerate(self.screws), 
                                   key=lambda x: vertebral_level_order(x[1].get("level", "")))
            
            for i, (original_idx, screw) in enumerate(sorted_screws):
                level = screw.get("level", "")
                diameter = screw.get("diameter", "")
                length = screw.get("length", "")
                
                screw_frame = tk.Frame(scrollable_frame, bg="white")
                screw_frame.pack(fill="x", pady=1)
                
                tk.Label(screw_frame, text=f"{i+1}. {level} - Ø{diameter}×{length}mm", 
                       bg="white").pack(side="left")
                
                # Add delete button
                tk.Button(screw_frame, text="×", command=lambda idx=original_idx: self.delete_implant("screw", idx),
                        bg="white", fg="red", bd=0, font=("Arial", 9, "bold")).pack(side="right")
        
        # Add cages to summary
        if self.cages:
            tk.Label(scrollable_frame, text="Cages:", bg="white", font=("Arial", 9, "bold")).pack(anchor="w", pady=(10,0))
            
            # Sort cages from cranial to caudal
            sorted_cages = sorted(enumerate(self.cages), 
                                  key=lambda x: vertebral_level_order(x[1].get("level", "")))
            
            for i, (original_idx, cage) in enumerate(sorted_cages):
                level = cage.get("level", "")
                width = cage.get("width", "")
                length = cage.get("length", "")
                height = cage.get("height", "")
                lordosis = cage.get("lordosis", "")
                
                cage_frame = tk.Frame(scrollable_frame, bg="white")
                cage_frame.pack(fill="x", pady=1)
                
                tk.Label(cage_frame, text=f"{i+1}. {level} - {width}×{length}×{height}mm {lordosis}°", 
                       bg="white").pack(side="left")
                
                # Add delete button
                tk.Button(cage_frame, text="×", command=lambda idx=original_idx: self.delete_implant("cage", idx),
                        bg="white", fg="red", bd=0, font=("Arial", 9, "bold")).pack(side="right")
        
        # Add mousewheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        
    def delete_implant(self, implant_type, index):
        """Remove an implant from the list and update display"""
        try:
            if implant_type == "screw" and 0 <= index < len(self.screws):
                del self.screws[index]
                self.show_status(f"Screw {index+1} deleted.", "info")
            elif implant_type == "cage" and 0 <= index < len(self.cages):
                del self.cages[index]
                self.show_status(f"Cage {index+1} deleted.", "info")
                
            self.update_implant_summary()
            self.display_image()
        except Exception as e:
            self.show_status(f"Failed to delete implant: {str(e)}", "error")

    def calculate_circle(self, p1, p2):
        center_x = (p1[0] + p2[0]) / 2
        center_y = (p1[1] + p2[1]) / 2
        radius = math.sqrt((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2) / 2
        return (center_x, center_y), radius

    def draw_landmarks(self):
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
        
        # Draw CBVA line
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
        
        # Draw C2-C7 lines
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
        
        # Draw T1 slope
        if all(k in lm for k in ["T1_ant", "T1_post"]):
            t1a_x, t1a_y = scaled(lm["T1_ant"])
            t1p_x, t1p_y = scaled(lm["T1_post"])
            self.canvas.create_line(t1a_x, t1a_y, t1p_x, t1a_y, fill=self.colors["T1"], width=1, dash=(4, 2))
            t1_slope = self.calculate_angle(lm["T1_ant"], lm["T1_post"])
            
            # Store T1 midpoint as anchor
            t1_anchor = ((t1a_x + t1p_x)/2, t1a_y - 20)
            store_anchor_point("T1Slope", t1_anchor)
            
            # Position T1 slope label
            label_x, label_y = get_label_position(t1_anchor, "T1Slope")
            # Add background
            bg = self.canvas.create_rectangle(
                label_x - 5, label_y - 5, 
                label_x + 120, label_y + 20, 
                fill='black', outline='white', width=1, stipple='gray50', 
                tags=("label:T1Slope", "bg")
            )
            
            # Create outlined text
            self.create_outlined_text(
                label_x, label_y, 
                text=f"T1 Slope: {t1_slope:.1f}°",
                fill_color=self.colors["T1"],
                font_size=self.text_size,
                tags=("label:T1Slope",)
            )
        
        # Draw Lumbar Lordosis (L1-L5)
        if all(k in lm for k in ["L1_ant", "L1_post", "L5_ant", "L5_post"]):
            l1a_x, l1a_y = scaled(lm["L1_ant"])
            l1p_x, l1p_y = scaled(lm["L1_post"])
            l5a_x, l5a_y = scaled(lm["L5_ant"])
            l5p_x, l5p_y = scaled(lm["L5_post"])
            
            # Draw L1 endplate
            self.canvas.create_line(l1a_x, l1a_y, l1p_x, l1p_y, fill=self.colors["Lumbar"], width=2)
            # Draw L5 endplate
            self.canvas.create_line(l5a_x, l5a_y, l5p_x, l5p_y, fill=self.colors["Lumbar"], width=2)
            # Connect endplates
            self.canvas.create_line(l1a_x, l1a_y, l5a_x, l5a_y, fill=self.colors["Lumbar"], width=1, dash=(5, 3))
            self.canvas.create_line(l1p_x, l1p_y, l5p_x, l5p_y, fill=self.colors["Lumbar"], width=1, dash=(5, 3))
            
            l1_angle = self.calculate_angle(lm["L1_ant"], lm["L1_post"])
            l5_angle = self.calculate_angle(lm["L5_ant"], lm["L5_post"])
            ll = abs(l1_angle - l5_angle)
            
            # Store L1-L5 midpoint as anchor
            ll_anchor = ((l1a_x + l5a_x)/2 - 25, (l1a_y + l5a_y)/2)
            store_anchor_point("LumbarLordosis", ll_anchor)
            
            # Position Lumbar Lordosis label
            label_x, label_y = get_label_position(ll_anchor, "LumbarLordosis") 
            # Add background
            bg = self.canvas.create_rectangle(
                label_x - 5, label_y - 5, 
                label_x + 180, label_y + 20, 
                fill='black', outline='white', width=1, stipple='gray50', 
                tags=("label:LumbarLordosis", "bg")
            )
            
            # Create outlined text
            self.create_outlined_text(
                label_x, label_y, 
                text=f"Lumbar Lordosis: {ll:.1f}°", 
                fill_color=self.colors["Lumbar"],
                font_size=self.text_size,
                tags=("label:LumbarLordosis",)
            )
        
        # Draw Sacral Slope
        if all(k in lm for k in ["S1_ant", "S1_post"]):
            s1a_x, s1a_y = scaled(lm["S1_ant"])
            s1p_x, s1p_y = scaled(lm["S1_post"])
            self.canvas.create_line(s1a_x, s1a_y, s1p_x, s1p_y, fill=self.colors["Sacral"], width=2)
            
            # Draw horizontal reference line
            self.canvas.create_line(s1a_x, s1a_y, s1p_x + 40, s1a_y, fill=self.colors["Sacral"], width=1, dash=(4, 2))
            
            s1_slope = self.calculate_angle(lm["S1_ant"], lm["S1_post"])
            
            # Store S1 anchor point
            s1_anchor = (s1p_x + 20, s1a_y - 15)
            store_anchor_point("SacralSlope", s1_anchor)
            
            # Position Sacral Slope label
            label_x, label_y = get_label_position(s1_anchor, "SacralSlope")
            # Add background
            bg = self.canvas.create_rectangle(
                label_x - 5, label_y - 5, 
                label_x + 150, label_y + 20, 
                fill='black', outline='white', width=1, stipple='gray50', 
                tags=("label:SacralSlope", "bg")
            )
            
            # Create outlined text
            self.create_outlined_text(
                label_x, label_y, 
                text=f"Sacral Slope: {s1_slope:.1f}°",
                fill_color=self.colors["Sacral"],
                font_size=self.text_size,
                tags=("label:SacralSlope",)
            )
        
        # Draw Pelvic Tilt and Pelvic Incidence
        if all(k in lm for k in ["S1_ant", "S1_post"]) and all(k in lm for k in ["LFH_edge1", "LFH_edge2", "RFH_edge1", "RFH_edge2"]):
            s1a_x, s1a_y = scaled(lm["S1_ant"])
            s1p_x, s1p_y = scaled(lm["S1_post"])
            
            # Calculate and draw left femoral head circle
            (lfh_center_img, lfh_radius_img) = self.calculate_circle(lm["LFH_edge1"], lm["LFH_edge2"])
            lfh_center_x, lfh_center_y = scaled(lfh_center_img)
            lfh_radius_scaled = lfh_radius_img * self.zoom
            self.canvas.create_oval(
                lfh_center_x - lfh_radius_scaled, lfh_center_y - lfh_radius_scaled,
                lfh_center_x + lfh_radius_scaled, lfh_center_y + lfh_radius_scaled,
                outline=self.colors["femoral"], width=2
            )
            
            # Calculate and draw right femoral head circle
            (rfh_center_img, rfh_radius_img) = self.calculate_circle(lm["RFH_edge1"], lm["RFH_edge2"])
            rfh_center_x, rfh_center_y = scaled(rfh_center_img)
            rfh_radius_scaled = rfh_radius_img * self.zoom
            self.canvas.create_oval(
                rfh_center_x - rfh_radius_scaled, rfh_center_y - rfh_radius_scaled,
                rfh_center_x + rfh_radius_scaled, rfh_center_y + rfh_radius_scaled,
                outline=self.colors["femoral"], width=2
            )
            
            # Calculate midpoint between femoral head centers
            bicoxo_x = (lfh_center_x + rfh_center_x) / 2
            bicoxo_y = (lfh_center_y + rfh_center_y) / 2
            
            # Calculate midpoint of sacral endplate
            s1_mid_x = (s1a_x + s1p_x) / 2
            s1_mid_y = (s1a_y + s1p_y) / 2
            
            # Draw line from bicoxofemoral axis to sacral midpoint
            self.canvas.create_line(bicoxo_x, bicoxo_y, s1_mid_x, s1_mid_y, fill=self.colors["Pelvic"], width=2)
            
            # Draw vertical reference line for pelvic tilt
            self.canvas.create_line(bicoxo_x, bicoxo_y, bicoxo_x, s1_mid_y, fill=self.colors["Pelvic"], width=1, dash=(4, 2))
            
            # Calculate perpendicular vector to sacral endplate
            dx_s1 = s1p_x - s1a_x
            dy_s1 = s1p_y - s1a_y
            length = 50  # Length of the perpendicular line to display
            
            # Calculate perpendicular vector (-dy, dx) and normalize
            magnitude = math.sqrt(dx_s1**2 + dy_s1**2)
            if magnitude > 0:
                perp_x = -dy_s1 / magnitude * length
                perp_y = dx_s1 / magnitude * length
                
                # Draw perpendicular line from sacral midpoint
                self.canvas.create_line(s1_mid_x, s1_mid_y, s1_mid_x + perp_x, s1_mid_y + perp_y, 
                                       fill=self.colors["Pelvic"], width=1, dash=(4, 2))
            
            # Calculate pelvic parameters in image coordinates
            lfh_center = lfh_center_img
            rfh_center = rfh_center_img
            bicoxo = ((lfh_center[0] + rfh_center[0]) / 2, (lfh_center[1] + rfh_center[1]) / 2)
            sacral_mid = ((lm["S1_ant"][0] + lm["S1_post"][0]) / 2, (lm["S1_ant"][1] + lm["S1_post"][1]) / 2)
            
            # Calculate pelvic tilt
            dx_pt = (sacral_mid[0] - bicoxo[0]) * px
            dy_pt = (sacral_mid[1] - bicoxo[1]) * py
            pt = abs(math.degrees(math.atan2(dx_pt, -dy_pt)))
            
            # Calculate pelvic incidence using the perpendicular
            # Sacral vector and its perpendicular
            sacral_vec = np.array([(lm["S1_post"][0] - lm["S1_ant"][0]) * px, (lm["S1_post"][1] - lm["S1_ant"][1]) * py])
            sacral_perp = np.array([-sacral_vec[1], sacral_vec[0]])
            sacral_perp = sacral_perp / np.linalg.norm(sacral_perp)
            
            # Vector from midpoint to bicoxofemoral axis
            hip_vec = np.array([(bicoxo[0] - sacral_mid[0]) * px, (bicoxo[1] - sacral_mid[1]) * py])
            hip_vec = hip_vec / np.linalg.norm(hip_vec)
            
            # Calculate PI as angle between these vectors
            cos_pi = np.clip(np.dot(sacral_perp, hip_vec), -1.0, 1.0)
            pi_angle = math.degrees(math.acos(cos_pi))
            
            # Store midpoint for PT label
            pt_x, pt_y = (bicoxo_x + s1_mid_x) / 2, (bicoxo_y + s1_mid_y) / 2
            
            # Store PT anchor point
            store_anchor_point("PelvicTilt", (pt_x, pt_y))
            
            # Position PT label
            label_x, label_y = get_label_position((pt_x + 20, pt_y), "PelvicTilt")
            # Add background
            bg = self.canvas.create_rectangle(
                label_x - 5, label_y - 5, 
                label_x + 130, label_y + 20, 
                fill='black', outline='white', width=1, stipple='gray50', 
                tags=("label:PelvicTilt", "bg")
            )
            
            # Create outlined text
            self.create_outlined_text(
                label_x, label_y, 
                text=f"Pelvic Tilt: {pt:.1f}°",
                fill_color=self.colors["Pelvic"],
                font_size=self.text_size,
                tags=("label:PelvicTilt",)
            )
            
            # Store PI anchor point (slightly below PT)
            store_anchor_point("PelvicIncidence", (pt_x, pt_y + 25))
            
            # Position PI label
            label_x, label_y = get_label_position((pt_x + 20, pt_y + 25), "PelvicIncidence")
            # Add background
            bg = self.canvas.create_rectangle(
                label_x - 5, label_y - 5, 
                label_x + 180, label_y + 20, 
                fill='black', outline='white', width=1, stipple='gray50', 
                tags=("label:PelvicIncidence", "bg")
            )
            
            # Create outlined text
            self.create_outlined_text(
                label_x, label_y, 
                text=f"Pelvic Incidence: {pi_angle:.1f}°",
                fill_color=self.colors["Pelvic"],
                font_size=self.text_size,
                tags=("label:PelvicIncidence",)
            )
                
        # Draw SVA (Sagittal Vertical Axis)
        if all(k in lm for k in ["C7_post", "S1_post"]):
            c7p_x, c7p_y = scaled(lm["C7_post"])
            s1p_x, s1p_y = scaled(lm["S1_post"])
            
            # Draw C7 plumbline
            self.canvas.create_line(c7p_x, c7p_y, c7p_x, s1p_y, fill=self.colors["SVA"], width=2, dash=(5, 3))
            
            # Draw horizontal line to S1
            self.canvas.create_line(c7p_x, s1p_y, s1p_x, s1p_y, fill=self.colors["SVA"], width=2)
            
            # Display SVA value
            sva = abs((lm['C7_post'][0] - lm['S1_post'][0]) * px)
            
            # Store SVA anchor point
            sva_anchor = ((c7p_x + s1p_x) / 2, s1p_y + 20)
            store_anchor_point("SVA", sva_anchor)
            
            # Position SVA label
            label_x, label_y = get_label_position(sva_anchor, "SVA")
            # Add background
            bg = self.canvas.create_rectangle(
                label_x - 5, label_y - 5, 
                label_x + 120, label_y + 20, 
                fill='black', outline='white', width=1, stipple='gray50', 
                tags=("label:SVA", "bg")
            )
            
            # Create outlined text
            self.create_outlined_text(
                label_x, label_y, 
                text=f"SVA: {sva:.1f}mm",
                fill_color=self.colors["SVA"],
                font_size=self.text_size,
                tags=("label:SVA",)
            )

    def draw_implants(self):
        # Helper function to convert image coordinates to canvas coordinates
        def scaled(pt):
            return pt[0] * self.zoom + self.offset[0], pt[1] * self.zoom + self.offset[1]
            
        # Draw screws
        for screw in self.screws:
            head_x, head_y = screw["head"]
            tip_x, tip_y = screw["tip"]
            
            # Convert to canvas coordinates
            sx1, sy1 = scaled((head_x, head_y))
            sx2, sy2 = scaled((tip_x, tip_y))
            
            # Draw the screw shaft
            self.canvas.create_line(sx1, sy1, sx2, sy2, fill='yellow', width=3)
            
            # Draw the screw head (larger circle)
            self.canvas.create_oval(sx1-5, sy1-5, sx1+5, sy1+5, fill='gold', outline='black')
            
            # Add text with screw info
            level = screw.get("level", "")
            diameter = screw.get("diameter", "")
            length = int(screw.get("length", 0))
            self.canvas.create_text(sx1+5, sy1-5, text=f"{level} Ø{diameter}x{length}mm", fill='white', anchor="sw")

        # Draw cages
        for cage in self.cages:
            corners = cage["corners"]
            level = cage.get("level", "")
            width = cage.get("width", "")
            length = cage.get("length", "")
            height = cage.get("height", "")
            lordosis = cage.get("lordosis", "")
            
            # Draw the cage outline
            polygon_points = []
            for x, y in corners:
                sx, sy = scaled((x, y))
                polygon_points.extend([sx, sy])
                
            # Draw the cage polygon with semi-transparent fill
            self.canvas.create_polygon(polygon_points, outline='orange', fill='orange', 
                                     stipple='gray50', width=2)
            
            # Label the cage
            center_x = sum(p[0] for p in corners) / len(corners)
            center_y = sum(p[1] for p in corners) / len(corners)
            sc_x, sc_y = scaled((center_x, center_y))
            
            # Draw the label with white background for visibility
            self.canvas.create_rectangle(sc_x-50, sc_y-10, sc_x+130, sc_y+10, 
                                       fill='black', stipple='gray50')
            self.canvas.create_text(sc_x, sc_y, text=f"{level} Cage {width}×{length}×{height}mm {lordosis}°", 
                                  fill='yellow', anchor="center")

    def draw_rod(self):
        if not self.rod_line:
            return
            
        # Helper function to convert image coordinates to canvas coordinates
        def scaled(pt):
            return pt[0] * self.zoom + self.offset[0], pt[1] * self.zoom + self.offset[1]
            
        points = self.rod_line["points"]
        side = self.rod_line["side"]
        diameter = self.rod_line["diameter"]
        
        # Color based on side
        color = 'blue' if side == 'Left' else 'green' if side == 'Right' else 'purple'
        
        # Draw points
        for x, y in points:
            sx, sy = scaled((x, y))
            self.canvas.create_oval(sx-3, sy-3, sx+3, sy+3, fill=color)
        
        # If we have more than 1 point, draw the spline curve
        if len(points) > 1:
            # Create a smoother curve with more points
            xy_points = np.array(points)
            x = xy_points[:, 0]
            y = xy_points[:, 1]
            
            # Check if we have enough unique points for a spline
            unique_points = len(np.unique(xy_points, axis=0))
            
            # Create the spline if we have enough unique points
            if unique_points >= 3:  # Need at least 3 unique points for cubic spline
                tck, u = splprep([x, y], s=0, k=min(unique_points-1, 3))  # k must be < unique_points
                unew = np.linspace(0, 1, 100)
                out = splev(unew, tck)
                spline_points = list(zip(out[0], out[1]))
                
                # Draw the spline
                for i in range(len(spline_points) - 1):
                    x1, y1 = spline_points[i]
                    x2, y2 = spline_points[i+1]
                    sx1, sy1 = scaled((x1, y1))
                    sx2, sy2 = scaled((x2, y2))
                    self.canvas.create_line(sx1, sy1, sx2, sy2, fill=color, width=float(diameter), smooth=True)
            else:
                # Not enough unique points for a spline, draw straight lines
                for i in range(len(points) - 1):
                    x1, y1 = points[i]
                    x2, y2 = points[i+1]
                    sx1, sy1 = scaled((x1, y1))
                    sx2, sy2 = scaled((x2, y2))
                    self.canvas.create_line(sx1, sy1, sx2, sy2, fill=color, width=float(diameter))
            
            # Add text with rod info
            x, y = points[0]
            sx, sy = scaled((x, y))
            self.canvas.create_text(sx, sy-10, text=f"{side} Rod Ø{diameter}mm", fill=color, anchor="sw")
    
    def calculate_angle(self, p1, p2):
        dx = (p2[0] - p1[0]) * self.pixel_spacing[1]
        dy = (p2[1] - p1[1]) * self.pixel_spacing[0]
        return math.degrees(math.atan2(-dy, dx))

    def update_measurements(self):
        target_dict = self.measurement_labels
        lm = self.landmarks
        px, py = self.pixel_spacing[1], self.pixel_spacing[0]
        
        def update(name, val):
            if name in target_dict:
                target_dict[name]["text"] = val

        update("CBVA", f"{math.degrees(math.atan2((lm['brow'][0]-lm['chin'][0])*px, -(lm['brow'][1]-lm['chin'][1])*py)):.2f}°") if all(k in lm for k in ["chin", "brow"]) else update("CBVA", "--")
        
        if all(k in lm for k in ["C2_ant", "C2_post", "C7_ant", "C7_post"]):
            c2 = self.calculate_angle(lm["C2_ant"], lm["C2_post"])
            c7 = self.calculate_angle(lm["C7_ant"], lm["C7_post"])
            update("C2–C7 Lordosis", f"{abs(c2 - c7):.2f}°")
        else:
            update("C2–C7 Lordosis", "--")
            
        update("C2–C7 SVA", f"{abs((lm['C2_post'][0] - lm['C7_post'][0]) * px):.2f} mm") if all(k in lm for k in ["C2_post", "C7_post"]) else update("C2–C7 SVA", "--")
        
        update("T1 Slope", f"{self.calculate_angle(lm['T1_ant'], lm['T1_post']):.2f}°") if all(k in lm for k in ["T1_ant", "T1_post"]) else update("T1 Slope", "--")
        
        if all(k in lm for k in ["L1_ant", "L1_post", "L5_ant", "L5_post"]):
            l1 = self.calculate_angle(lm["L1_ant"], lm["L1_post"])
            l5 = self.calculate_angle(lm["L5_ant"], lm["L5_post"])
            update("Lumbar Lordosis", f"{abs(l1 - l5):.2f}°")
        else:
            update("Lumbar Lordosis", "--")
            
        update("Sacral Slope", f"{self.calculate_angle(lm['S1_ant'], lm['S1_post']):.2f}°") if all(k in lm for k in ["S1_ant", "S1_post"]) else update("Sacral Slope", "--")
        
        if all(k in lm for k in ["S1_ant", "S1_post"]) and all(k in lm for k in ["LFH_edge1", "LFH_edge2", "RFH_edge1", "RFH_edge2"]):
            # Calculate femoral head centers
            lfh_center, _ = self.calculate_circle(lm["LFH_edge1"], lm["LFH_edge2"])
            rfh_center, _ = self.calculate_circle(lm["RFH_edge1"], lm["RFH_edge2"])
            
            # Calculate bicoxofemoral axis (midpoint between femoral heads)
            bicoxo = ((lfh_center[0] + rfh_center[0]) / 2, (lfh_center[1] + rfh_center[1]) / 2)
            
            # Calculate sacral midpoint
            sacral_mid = ((lm["S1_ant"][0] + lm["S1_post"][0]) / 2, (lm["S1_ant"][1] + lm["S1_post"][1]) / 2)
            
            # Calculate PT
            dx_pt = (sacral_mid[0] - bicoxo[0]) * px
            dy_pt = (sacral_mid[1] - bicoxo[1]) * py
            pt = abs(math.degrees(math.atan2(dx_pt, -dy_pt)))
            update("Pelvic Tilt", f"{pt:.2f}°")
            
            # Calculate PI using the perpendicular to sacral endplate
            sacral_vec = np.array([(lm["S1_post"][0] - lm["S1_ant"][0]) * px, (lm["S1_post"][1] - lm["S1_ant"][1]) * py])
            sacral_perp = np.array([-sacral_vec[1], sacral_vec[0]])
            sacral_perp = sacral_perp / np.linalg.norm(sacral_perp)
            
            hip_vec = np.array([(bicoxo[0] - sacral_mid[0]) * px, (bicoxo[1] - sacral_mid[1]) * py])
            hip_vec = hip_vec / np.linalg.norm(hip_vec)
            
            cos_pi = np.clip(np.dot(sacral_perp, hip_vec), -1.0, 1.0)
            pi_angle = math.degrees(math.acos(cos_pi))
            
            update("PI (vector)", f"{pi_angle:.2f}°")
        else:
            update("Pelvic Tilt", "--")
            update("PI (vector)", "--")
            
        update("SVA", f"{abs((lm['C7_post'][0] - lm['S1_post'][0]) * px):.2f} mm") if all(k in lm for k in ["C7_post", "S1_post"]) else update("SVA", "--")

    def place_screw(self):
        """Begin placing a screw on the image"""
        self.current_screw = "placing"
        self.osteotomy_points = []
        level = self.level_var.get()
        self.show_status(
            f"Click to set the screw head/entry point at {level}, then click to set the trajectory/tip.",
            "info",
            persistent=True  # Keep instruction visible throughout the process
        )
        
    def generate_rod_model(self):
        """Generate a rod model based on placed screw heads"""
        # Clear any existing rod first, regardless of whether we'll create a new one
        self.rod_line = None
        
        if not self.screws:
            self.show_status("Place at least 2 screws first to generate a rod model.", "error")
            return
        
        if len(self.screws) < 2:
            self.show_status("Place at least 2 screws first to generate a rod model.", "error")
            self.display_image()  # Refresh display to remove any previous rod
            return
            
        # Get all screw heads and sort them by y-coordinate (vertically)
        screw_heads = [(screw["head"], screw["level"]) for screw in self.screws]
        screw_heads.sort(key=lambda x: x[0][1])  # Sort by y-coordinate
        
        # Extract just the points in the sorted order
        rod_points = [point for point, _ in screw_heads]
        
        # Create the rod line data
        self.rod_line = {
            "points": rod_points,
            "side": self.rod_side.get(),
            "diameter": self.rod_diameter.get()
        }
        
        # Display the rod
        self.display_image()
        self.show_status(f"Rod generated: {self.rod_side.get()} side, {self.rod_diameter.get()}mm diameter", "success")
        
    def export_rod_as_stl(self):
        """Export the rod model as STL for 3D printing"""
        if not self.rod_line:
            self.show_status("Generate a rod model first.", "error")
            return
            
        # Get file save location
        filepath = filedialog.asksaveasfilename(
            defaultextension=".stl",
            filetypes=[("STL files", "*.stl"), ("All files", "*.*")]
        )
        
        if not filepath:
            return
            
        # Generate STL file for the rod
        try:
            # Get rod parameters
            points = self.rod_line["points"]
            diameter = float(self.rod_line["diameter"])
            side = self.rod_line["side"]
            
            # Convert points to numpy array
            points = np.array(points)
            
            # Create smoother curve with spline interpolation
            if len(points) >= 2:
                # Check if we have enough unique points for a spline
                unique_points = len(np.unique(points, axis=0))
                if unique_points >= 3:
                    # Create a spline through the points
                    tck, u = splprep([points[:, 0], points[:, 1]], s=0)
                    
                    # Sample points along the spline
                    u_new = np.linspace(0, 1, 100)
                    new_points = np.array(splev(u_new, tck)).T
                else:
                    # Not enough unique points, use linear interpolation
                    t = np.linspace(0, 1, 100)
                    new_points = np.zeros((100, 2))
                    
                    # Simple linear interpolation between available points
                    for i in range(100):
                        idx = i * (len(points) - 1) / 99  # Map 0-99 to 0-(len(points)-1)
                        idx_low = int(np.floor(idx))
                        idx_high = int(np.ceil(idx))
                        if idx_low == idx_high:
                            new_points[i] = points[idx_low]
                        else:
                            weight = idx - idx_low
                            new_points[i] = (1 - weight) * points[idx_low] + weight * points[idx_high]
        
                
                # Create a 3D representation (add z-coordinate)
                # Here we're creating a simple 2.5D model since we only have a 2D image
                z_coord = np.zeros(len(new_points))
                points_3d = np.column_stack((new_points, z_coord))
                
                # Create a cylinder mesh along the spline
                # For simplicity, we'll create a rough approximation with triangles
                vertices = []
                faces = []
                
                # Create vertices around the spline path
                segments = len(points_3d) - 1
                segments_around = 8  # number of segments around the circumference
                
                # Calculate normals and tangents for each point on the spline
                tangents = np.zeros((len(points_3d), 3))
                normals = np.zeros((len(points_3d), 3))
                
                # For first and last points
                tangents[0] = points_3d[1] - points_3d[0]
                tangents[-1] = points_3d[-1] - points_3d[-2]
                
                # For middle points
                for i in range(1, len(points_3d) - 1):
                    tangents[i] = (points_3d[i+1] - points_3d[i-1]) / 2
                
                # Normalize tangents
                for i in range(len(tangents)):
                    tangents[i] = tangents[i] / np.linalg.norm(tangents[i])
                    
                # Choose a consistent normal direction
                first_normal = np.array([0, 0, 1])  # Start with z-axis
                
                # Calculate normals perpendicular to tangents
                for i in range(len(normals)):
                    normal = np.cross(tangents[i], first_normal)
                    normal = normal / np.linalg.norm(normal)
                    normals[i] = normal
                    
                # Calculate binormals (perpendicular to both tangent and normal)
                binormals = np.zeros((len(points_3d), 3))
                for i in range(len(binormals)):
                    binormals[i] = np.cross(tangents[i], normals[i])
                    binormals[i] = binormals[i] / np.linalg.norm(binormals[i])
                
                # Generate vertices around the spline path
                for i in range(len(points_3d)):
                    for j in range(segments_around):
                        angle = 2 * np.pi * j / segments_around
                        
                        # Calculate position on circle
                        circle_x = np.cos(angle) * diameter / 2
                        circle_y = np.sin(angle) * diameter / 2
                        
                        # Position in 3D space
                        pos = points_3d[i] + circle_x * normals[i] + circle_y * binormals[i]
                        vertices.append(pos)
                
                # Generate faces (triangles)
                for i in range(segments):
                    for j in range(segments_around):
                        # Calculate vertex indices
                        v0 = i * segments_around + j
                        v1 = i * segments_around + (j + 1) % segments_around
                        v2 = (i + 1) * segments_around + j
                        v3 = (i + 1) * segments_around + (j + 1) % segments_around
                        
                        # Add two triangles for each quad
                        faces.append([v0, v1, v2])
                        faces.append([v1, v3, v2])
                
                # Create and save the STL mesh
                vertices = np.array(vertices)
                faces = np.array(faces)
                
                # Create the mesh
                rod_mesh = mesh.Mesh(np.zeros(len(faces), dtype=mesh.Mesh.dtype))
                for i, f in enumerate(faces):
                    for j in range(3):
                        rod_mesh.vectors[i][j] = vertices[f[j]]
                
                # Add caps at the ends for a complete model
                # This adds simple flat end caps
                
                # Center points for the end caps
                start_center = points_3d[0]
                end_center = points_3d[-1]
                
                # Add center points to vertices list
                start_center_index = len(vertices)
                vertices = np.vstack((vertices, start_center))
                
                end_center_index = len(vertices)
                vertices = np.vstack((vertices, end_center))
                
                # Create triangles for start cap
                start_cap_faces = []
                for j in range(segments_around):
                    v0 = start_center_index
                    v1 = j
                    v2 = (j + 1) % segments_around
                    start_cap_faces.append([v0, v2, v1])  # Note: reversed for normal direction
                
                # Create triangles for end cap
                end_cap_faces = []
                for j in range(segments_around):
                    v0 = end_center_index
                    v1 = segments * segments_around + j
                    v2 = segments * segments_around + (j + 1) % segments_around
                    end_cap_faces.append([v0, v1, v2])
                
                # Combine all faces
                all_faces = np.vstack((faces, start_cap_faces, end_cap_faces))
                
                # Create the final mesh
                final_mesh = mesh.Mesh(np.zeros(len(all_faces), dtype=mesh.Mesh.dtype))
                for i, f in enumerate(all_faces):
                    for j in range(3):
                        final_mesh.vectors[i][j] = vertices[f[j]]
                
                # Save the mesh to STL file
                final_mesh.save(filepath)
                
                self.show_status(f"Rod model successfully exported to {filepath}", "success")
                
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export STL: {str(e)}")

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
            self.show_status("No image loaded to save.", "error")
            return

        # Step 1: Ensure all drawing operations are complete
        self.canvas.update_idletasks()

        # Step 2: Capture the canvas using platform-specific method
        # Use platform-specific method for capture
        if sys.platform == "win32":
            shot = self._grab_canvas_via_gdi()
        else:
            # Fallback for Mac/Linux
            x = self.root.winfo_rootx() + self.canvas.winfo_x()
            y = self.root.winfo_rooty() + self.canvas.winfo_y()
            w = self.canvas.winfo_width()
            h = self.canvas.winfo_height()
            shot = ImageGrab.grab((x, y, x+w, y+h))
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
                self.show_status(f"Screenshot saved to: {path}", "success")
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
        
def fix_recursive_limit():
    """Increase recursion limit to handle complex operations"""
    current = sys.getrecursionlimit()
    sys.setrecursionlimit(current * 5)

if __name__ == "__main__":
    # Fix recursion limit before creating the main window
    fix_recursive_limit()
    
    # Create the root window first
    root = tk.Tk()
    root.geometry("1200x800")  # Set initial window size
    
    # Allow the window to initialize fully before creating the application
    root.update()
    
    # Create the application instance
    app = SpineForgePlanner(root)
    
    # Start the main event loop
    root.mainloop()
        