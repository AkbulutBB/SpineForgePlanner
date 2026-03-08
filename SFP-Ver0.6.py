# -*- coding: utf-8 -*-
"""
SpineForge Planner - Ver 0.6
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
        self.root.title("SpineForge Planner - Ver 0.6")
        
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
        
        # Add these lines in your __init__ method after the existing state variables
        self.is_calibrated = False
        self.calibration_mode = False
        self.calibration_points = []
        self.calibration_line_id = None
        self.calibration_angle = None
       
        self.current_file_path = None  # Track the currently loaded file
        
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
        
        # Add these lines after the existing initialization variables (around line with self.screws = [])
        self.measurements = []  # Store distance and angle measurements
        self.measurement_points = []  # Temporary storage for measurement creation
        self.current_measurement_tool = None  # Track active measurement tool
        self.dragging_measurement = None  # For dragging measurement points
        self.dragging_measurement_point = None  # Which point is being dragged
        self.measurement_drag_start = None  # Start position for dragging
        
        # Implant state
        self.screws = []
        self.current_screw = None
        self.cages = []              # kept for legacy drawing code
        self.corpectomy_cages = []   # kept for legacy drawing code
        self.cage_points = []        # kept for legacy drawing code
        self.current_cage_type = None

        # New cage-simulation state  (mirrors osteotomy stack pattern)
        self.applied_cages       = []    # committed cage transforms
        self.current_cage_mode   = None  # "place_bottom" | "preview" | "confirm"
        self.cage_bottom_pt      = None  # (x,y) inferior endplate – pivot
        self.cage_top_orig       = None  # (x,y) superior endplate – locked
        self.cage_top_current    = None  # (x,y) live cursor while in preview
        self.cage_rotation_angle = 0.0
        
        # Cage interaction state
        self.dragging_cage = None
        self.cage_drag_start = None
        self.resizing_cage = False
        self.resizing_handle = None
        self.selected_cage = None
        self.cage_handles = []
        
        self.applied_cages     = []   # committed cage transforms (the reversible stack)
        self.cage_corners      = []   # [(inf_ant), (inf_post), (sup_ant), (sup_post)]
        self.current_cage_mode = None # "place_inf_ant"|"place_inf_post"|
                                      # "place_sup_ant"|"place_sup_post"|
                                      # "adjust"|"confirm"
        self.cage_handle_pos   = None # cursor position during adjust/confirm
        
        self.dragging_screw = None
        self.dragging_screw_part = None  # 'head' or 'tip'
        self.screw_drag_start = None
        
        # Rod state
        self.rod_points = []
        self.rod_line = None
        self.rod_model = None
        
        # Osteotomy state
        self.osteotomies = []  # List of osteotomies instead of single osteotomy
        self.current_osteotomy_points = []  # Current osteotomy being placed
        self.current_osteotomy = None
        self.osteotomy_applied = False
        self.original_landmarks = {}  # Store original positions before osteotomy
        self.osteotomy_angle = 0  # Track the correction angle
        
        # Create a main frame that will contain all UI elements
        self.main_frame = tk.Frame(root)
        self.main_frame.pack(fill="both", expand=True)
        
        # Now create the UI elements with the new layout
        # Left sidebar for tools
        self.sidebar = tk.Frame(self.main_frame, width=400, bg="lightgray")
        self.sidebar.pack(side="left", fill="y")
    
        # Replace the existing status_label section with this:
        # Create a frame for file info and status
        info_frame = tk.Frame(self.sidebar, bg="lightgray")
        info_frame.pack(pady=(5,0), fill="x", padx=5)
        
        # File path label (shows currently loaded file)
        self.file_path_label = tk.Label(info_frame, text="No file loaded", bg="lightgray", 
                                        fg="darkblue", font=("Arial", 9), anchor="w", justify="left")
        self.file_path_label.pack(fill="x", pady=(0,2))
        
        # Status label (for operations feedback)
        self.status_label = tk.Label(info_frame, text="", bg="lightgray", fg="green", font=("Arial", 10))
        self.status_label.pack(pady=(0,5))

        # Top row for file actions
        # Replace the file_frame section with this:
        file_frame = tk.Frame(self.sidebar, bg="lightgray")
        file_frame.pack(pady=5)
        self.load_button = tk.Button(file_frame, text="Load Image", command=self.load_image)
        self.load_button.pack(side="left", padx=2)
        self.calibrate_button = tk.Button(file_frame, text="Calibrate Image", command=self.start_calibration)
        self.calibrate_button.pack(side="left", padx=2)
        self.save_button = tk.Button(file_frame, text="Save Screenshot", command=self.save_screenshot)
        self.save_button.pack(side="left", padx=2)
        self.copy_button = tk.Button(file_frame, text="Copy Results", command=self.copy_to_clipboard)
        self.copy_button.pack(side="left", padx=2)
        
        self.flip_button = tk.Button(file_frame, text="Flip H", command=self.flip_image_horizontal)
        self.flip_button.pack(side="left", padx=2)

        # Image enhancement controls (brightness and contrast)
        enhancement_frame = tk.Frame(self.sidebar, bg="lightgray")
        enhancement_frame.pack(pady=5, fill="x")
        
        # Brightness control
        brightness_subframe = tk.Frame(enhancement_frame, bg="lightgray")
        brightness_subframe.pack(fill="x", pady=2)
        tk.Label(brightness_subframe, text="Brightness:", bg="lightgray").pack(side="left", padx=5)
        self.brightness_slider = tk.Scale(brightness_subframe, from_=0.3, to=2.5, resolution=0.1, 
                                         orient="horizontal", command=self.update_image_enhancement)
        self.brightness_slider.set(1.0)
        self.brightness_slider.pack(side="left", fill="x", expand=True, padx=5)
        
        # Contrast control  
        contrast_subframe = tk.Frame(enhancement_frame, bg="lightgray")
        contrast_subframe.pack(fill="x", pady=2)
        tk.Label(contrast_subframe, text="Contrast:   ", bg="lightgray").pack(side="left", padx=5)
        self.contrast_slider = tk.Scale(contrast_subframe, from_=0.3, to=3.0, resolution=0.1, 
                                       orient="horizontal", command=self.update_image_enhancement)
        self.contrast_slider.set(1.0)
        self.contrast_slider.pack(side="left", fill="x", expand=True, padx=5)
        
        # Reset button for image enhancements
        reset_enhancement_btn = tk.Button(enhancement_frame, text="Reset", 
                                         command=self.reset_image_enhancement, bg="lightcoral")
        reset_enhancement_btn.pack(pady=2)
        
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
        
        # Create sub-tabs for different implant types
        self.implant_notebook = ttk.Notebook(self.implant_tab)
        self.implant_notebook.pack(fill="both", expand=True, pady=5)
        
        # Screws sub-tab
        self.screw_tab = tk.Frame(self.implant_notebook, bg="lightgray")
        self.implant_notebook.add(self.screw_tab, text="Pedicle Screws")
        

        # Setup each sub-tab
        self.cage_tab = tk.Frame(self.implant_notebook, bg="lightgray")
        self.implant_notebook.add(self.cage_tab, text="Cage")
        self.setup_screw_tab()
        self.setup_cage_tab()
        
        # Rod Export Tab
        self.rod_tab = tk.Frame(self.tab_control, bg="lightgray")
        self.tab_control.add(self.rod_tab, text="Rod Export")
        
        # Osteotomy Tab
        self.osteotomy_tab = tk.Frame(self.tab_control, bg="lightgray")
        self.tab_control.add(self.osteotomy_tab, text="Osteotomy")

        # Landmark buttons in two columns
        button_frame = tk.Frame(self.landmark_tab, bg="lightgray")
        button_frame.pack(pady=5)
        self.point_buttons = [
            ("Brow", "brow"), ("Chin", "chin"),
            ("C2 Ant", "C2_ant"), ("C2 Post", "C2_post"),
            ("C7 Ant", "C7_ant"), ("C7 Post", "C7_post"),
            ("T1 Ant", "T1_ant"), ("T1 Post", "T1_post"),
            ("L1 Ant", "L1_ant"), ("L1 Post", "L1_post"),
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

        # Add measurement tools section to landmarks tab (add this after the point buttons)
        measurement_tools_frame = tk.Frame(self.landmark_tab, bg="lightgray")
        measurement_tools_frame.pack(pady=(20, 5), fill="x")
        
        tk.Label(measurement_tools_frame, text="Measurement Tools:", bg="lightgray", 
                 font=("Arial", 10, "bold")).pack(anchor="w", padx=5)
        
        tools_button_frame = tk.Frame(measurement_tools_frame, bg="lightgray")
        tools_button_frame.pack(pady=5)
        
        # Length measurement button
        length_btn = tk.Button(tools_button_frame, text="Length", 
                              command=lambda: self.start_measurement_tool("length"),
                              bg="lightblue", width=10)
        length_btn.pack(side="left", padx=2)
        
        # Angle measurement button  
        angle_btn = tk.Button(tools_button_frame, text="Angle",
                             command=lambda: self.start_measurement_tool("angle"),
                             bg="lightgreen", width=10)
        angle_btn.pack(side="left", padx=2)
        
        # Instructions for measurements
        tk.Label(measurement_tools_frame, 
                 text="Length: Click two points to measure distance\n"
                 "Angle: Click three points to measure angle\n"
                 "Ctrl+Alt+Click to drag the points",
                 bg="lightgray", justify="left", font=("Arial", 8)).pack(anchor="w", padx=5)
                
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
        
        # Osteotomy options
        osteotomy_frame = tk.Frame(self.osteotomy_tab, bg="lightgray")
        osteotomy_frame.pack(pady=5, fill="x")
        
        tk.Label(osteotomy_frame, text="Wedge Osteotomy:", bg="lightgray", font=("Arial", 10, "bold")).pack(anchor="w", padx=5)
        
        # Instructions
        instruction_text = (
            "1. Click anterior point of wedge\n"
            "2. Click superior posterior point\n"
            "3. Click inferior posterior point\n"
            "4. Apply osteotomy to simulate correction"
        )
        tk.Label(osteotomy_frame, text=instruction_text, bg="lightgray", justify="left", font=("Arial", 9)).pack(anchor="w", padx=20, pady=5)
        
        # Vertebral Level for osteotomy
        tk.Label(osteotomy_frame, text="Osteotomy Level:", bg="lightgray").pack(anchor="w", padx=5, pady=(10,0))
        osteotomy_level_frame = tk.Frame(osteotomy_frame, bg="lightgray")
        osteotomy_level_frame.pack(fill="x", padx=5, pady=2)
        
        self.osteotomy_level_var = tk.StringVar(value="L3")
        self.osteotomy_level_dropdown = ttk.Combobox(osteotomy_level_frame, textvariable=self.osteotomy_level_var)
        self.osteotomy_level_dropdown['values'] = ('C3', 'C4', 'C5', 'C6', 'C7',
                                                   'T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8', 'T9', 'T10', 'T11', 'T12',
                                                   'L1', 'L2', 'L3', 'L4', 'L5', 'S1', 'S2')
        self.osteotomy_level_dropdown.pack(side="left", fill="x", expand=True)
        
        # Buttons
        button_frame = tk.Frame(osteotomy_frame, bg="lightgray")
        button_frame.pack(fill="x", padx=5, pady=10)
        
        self.place_osteotomy_button = tk.Button(button_frame, text="Place Wedge Osteotomy", command=self.place_wedge_osteotomy)
        self.place_osteotomy_button.pack(pady=2, fill="x")
        
        self.apply_osteotomy_button = tk.Button(button_frame, text="Apply Osteotomy", command=self.apply_osteotomy, state="disabled")
        self.apply_osteotomy_button.pack(pady=2, fill="x")
        
        self.reset_osteotomy_button = tk.Button(button_frame, text="Reset Osteotomy", command=self.reset_osteotomy, state="disabled")
        self.reset_osteotomy_button.pack(pady=2, fill="x")
        
        # Predicted correction display
        self.correction_frame = tk.Frame(osteotomy_frame, bg="white", relief="sunken", bd=1)
        self.correction_frame.pack(fill="x", padx=5, pady=5)
        
        tk.Label(self.correction_frame, text="Predicted Correction:", bg="white", font=("Arial", 9, "bold")).pack(anchor="w", padx=5, pady=2)
        self.correction_label = tk.Label(self.correction_frame, text="Place osteotomy points first", bg="white", font=("Arial", 9))
        self.correction_label.pack(anchor="w", padx=15, pady=2)
        
        # Center panel for the image
        self.center_panel = tk.Frame(self.main_frame)
        self.center_panel.pack(side="left", fill="both", expand=True)
        
        # Canvas to show image
        self.canvas = tk.Canvas(self.center_panel, bg="black", cursor="cross")
        self.canvas.pack(fill="both", expand=True)
        
        # Right sidebar for measurements and results and status
        self.right_sidebar_container = tk.Frame(self.main_frame, width=350)
        self.right_sidebar_container.pack(side="right", fill="y")
        
        # Add scrollbar to the container
        right_scrollbar = tk.Scrollbar(self.right_sidebar_container)
        right_scrollbar.pack(side="right", fill="y")
        
        # Create canvas for scrolling
        right_canvas = tk.Canvas(self.right_sidebar_container, bg="lightgray", 
                                yscrollcommand=right_scrollbar.set, highlightthickness=0)
        right_canvas.pack(side="left", fill="both", expand=True)        
        
        # Configure scrollbar
        right_scrollbar.config(command=right_canvas.yview)
        
        # Create the actual right sidebar inside the canvas
        self.right_sidebar = tk.Frame(right_canvas, width=350, bg="lightgray")
        self.right_sidebar.bind("<Configure>", 
                               lambda e: right_canvas.configure(scrollregion=right_canvas.bbox("all")))

        # Create window in canvas
        right_canvas.create_window((0, 0), window=self.right_sidebar, anchor="nw")
        
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
        
        # Calibration status display
        self.calib_frame = tk.Frame(self.sidebar, bg="lightgray")
        self.calib_frame.pack(fill="x", padx=5, pady=2)
        self.calib_status = tk.Label(self.calib_frame, text="Not calibrated", bg="lightcoral", 
                                    fg="white", font=("Arial", 9, "bold"))
        self.calib_status.pack(fill="x")
        
        def _on_sidebar_mousewheel(event):
            right_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        right_canvas.bind("<MouseWheel>", _on_sidebar_mousewheel)

        
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
        
        # Add this after the existing measurements section in __init__
        # Estimated results section (for post-osteotomy predictions)
        self.estimated_label = tk.Label(self.right_sidebar, text="Estimated Post-Osteotomy:", 
                                       bg="lightgray", font=("Arial", 10, "bold"))
        self.estimated_label.pack(pady=(20,5))
        
        # Create a frame for estimated results
        estimated_container = tk.Frame(self.right_sidebar, bg="white")
        estimated_container.pack(fill="x", padx=5, pady=5)
        
        # Add scrollbar for estimated results
        estimated_scrollbar = tk.Scrollbar(estimated_container)
        estimated_scrollbar.pack(side="right", fill="y")
        
        # Create a canvas for estimated results
        estimated_canvas = tk.Canvas(estimated_container, bg="white", 
                                   yscrollcommand=estimated_scrollbar.set,
                                   highlightthickness=0)
        estimated_canvas.pack(side="left", fill="both", expand=True)
        
        # Configure the scrollbar
        estimated_scrollbar.config(command=estimated_canvas.yview)
        
        # Create a frame inside the canvas for estimated measurements
        self.estimated_frame = tk.Frame(estimated_canvas, bg="white")
        self.estimated_frame.bind("<Configure>", 
                                 lambda e: estimated_canvas.configure(
                                     scrollregion=estimated_canvas.bbox("all")))
        
        # Create a window inside the canvas
        estimated_canvas.create_window((0, 0), window=self.estimated_frame, 
                                      anchor="nw", width=estimated_canvas.winfo_width())
        
        # Add estimated measurement labels
        self.estimated_labels = {}
        measurement_names = [
            "CBVA", "C2–C7 Lordosis", "C2–C7 SVA", "T1 Slope", "Lumbar Lordosis",
            "Sacral Slope", "Pelvic Tilt", "PI (vector)", "SVA"
        ]
        
        for name in measurement_names:
            row = tk.Frame(self.estimated_frame, bg="white")
            row.pack(fill="x", pady=1)
            label = tk.Label(row, text=f"{name}:", anchor="w", width=20, bg="white")
            label.pack(side="left")
            val_label = tk.Label(row, text="--", anchor="w", bg="white")
            val_label.pack(side="left")
            # Add change indicator
            change_label = tk.Label(row, text="", anchor="w", bg="white", fg="green")
            change_label.pack(side="left", padx=(10,0))
            self.estimated_labels[name] = {"value": val_label, "change": change_label}
        
        # Initially hide the estimated results section
        self.estimated_label.pack_forget()
        estimated_container.pack_forget()
        self.estimated_container = estimated_container
        
        # Implant summary section
        self.implant_summary_label = tk.Label(self.right_sidebar, text="Implants:", bg="lightgray")
        self.implant_summary_label.pack(pady=(20,5))
        
        # Frame for implant list
        self.implant_list_frame = tk.Frame(self.right_sidebar, bg="white")
        self.implant_list_frame.pack(fill="x", padx=5, pady=5)
        
        # Measurements Tab - Add this RIGHT AFTER the implants tab in setup_right_sidebar()
        # (This should go in the RIGHT sidebar tab control, not the main tab control)
        self.measurements_tab = tk.Frame(self.tab_control, bg="lightgray")  # Use RIGHT sidebar tab_control
        self.tab_control.add(self.measurements_tab, text="Measurements")
        self.setup_measurements_tab()
        
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
        
        # Add screw dragging bindings (using Ctrl+click to avoid conflicts)
        self.canvas.bind("<Control-Button-1>", self.start_drag_screw)
        self.canvas.bind("<Control-B1-Motion>", self.on_drag_screw)
        self.canvas.bind("<Control-ButtonRelease-1>", self.stop_drag_screw)
        
        # Add cage dragging bindings
        self.canvas.bind("<Alt-Button-1>", self.start_drag_cage)
        self.canvas.bind("<Alt-B1-Motion>", self.on_drag_cage)
        self.canvas.bind("<Alt-ButtonRelease-1>", self.stop_drag_cage)
        
        # Cage resize bindings (Shift+Click to select and show handles)
        self.canvas.bind("<Shift-Button-1>", self.select_cage_for_resize)
        self.canvas.bind("<Button-1>", self.handle_cage_interaction, add="+")
        self.canvas.bind("<B1-Motion>", self.handle_cage_drag_or_resize, add="+")
        self.canvas.bind("<ButtonRelease-1>", self.handle_cage_release, add="+")
        
        # Add measurement dragging bindings (add this after the existing cage bindings)
        self.canvas.bind("<Control-Alt-Button-1>", self.start_drag_measurement)
        self.canvas.bind("<Control-Alt-B1-Motion>", self.on_drag_measurement)
        self.canvas.bind("<Control-Alt-ButtonRelease-1>", self.stop_drag_measurement)
        
        self.canvas.bind("<Motion>", self.on_mouse_motion)
        
        # Set initial instruction
        self.info_label.config(text="Load a DICOM image to begin")


    # ──────────────────────────────────────────────────────────────────────────────
    # C)  New / replacement methods  –  paste into SpineForgePlanner class
    # ──────────────────────────────────────────────────────────────────────────────
    
        # ─────────────────────────────────────────────────────────────────────────
        # UI
        # ─────────────────────────────────────────────────────────────────────────

    def setup_cage_tab(self):
        """Unified cage simulation tab – replaces interbody + corpectomy tabs."""
        outer = tk.Frame(self.cage_tab, bg="lightgray")
        outer.pack(fill="both", expand=True, padx=2, pady=2)
    
        tk.Label(outer, text="Cage Simulation", bg="lightgray",
                 font=("Arial", 10, "bold")).pack(anchor="w", padx=5, pady=(5, 0))
    
        tk.Label(outer, text="Level:", bg="lightgray").pack(anchor="w", padx=5, pady=(6, 0))
        self.cage_level_var = tk.StringVar(value="L4-L5")
        cb = ttk.Combobox(outer, textvariable=self.cage_level_var, width=14)
        cb["values"] = (
            "C3-C4", "C4-C5", "C5-C6", "C6-C7", "C7-T1",
            "T12-L1", "L1-L2", "L2-L3", "L3-L4", "L4-L5", "L5-S1",
            "L1 corp", "L2 corp", "L3 corp", "L4 corp", "L5 corp",
        )
        cb.pack(anchor="w", padx=5, pady=2, fill="x")
    
        instr = (
            "1. Click 'Place Cage'\n"
            "2. Click: Inf.Ant → Inf.Post → Sup.Ant → Sup.Post\n"
            "3. Move cursor: Y = height | X = lordosis\n"
            "4. Click to lock → 'Apply Cage'"
        )
        tk.Label(outer, text=instr, bg="lightgray", justify="left",
                 font=("Arial", 8)).pack(anchor="w", padx=10, pady=5)
    
        rf = tk.Frame(outer, bg="white", relief="sunken", bd=1)
        rf.pack(fill="x", padx=5, pady=3)
        tk.Label(rf, text="Live measurements:", bg="white",
                 font=("Arial", 8, "bold")).pack(anchor="w", padx=5, pady=(3, 0))
        self.cage_ant_h_label  = tk.Label(rf, text="Ant height:  —", bg="white", font=("Arial", 9))
        self.cage_ant_h_label.pack(anchor="w", padx=10)
        self.cage_post_h_label = tk.Label(rf, text="Post height: —", bg="white", font=("Arial", 9))
        self.cage_post_h_label.pack(anchor="w", padx=10)
        self.cage_lord_label   = tk.Label(rf, text="Lordosis:    —", bg="white", font=("Arial", 9))
        self.cage_lord_label.pack(anchor="w", padx=10, pady=(0, 4))
    
        bf = tk.Frame(outer, bg="lightgray")
        bf.pack(fill="x", padx=5, pady=6)
        self.place_cage_btn = tk.Button(bf, text="Place Cage",
                                        command=self.start_cage_placement)
        self.place_cage_btn.pack(fill="x", pady=3, ipady=4)
        self.apply_cage_btn = tk.Button(bf, text="Apply Cage",
                                        command=self.apply_cage, state="disabled")
        self.apply_cage_btn.pack(fill="x", pady=3, ipady=4)
        self.reset_cage_btn = tk.Button(bf, text="Reset All Cages",
                                        command=self.reset_all_cages, state="disabled")
        self.reset_cage_btn.pack(fill="x", pady=3, ipady=4)
    
    def start_cage_placement(self):
        """Begin 4-point cage placement workflow."""
        if not self.image:
            self.show_status("Load an image first.", "error")
            return
        self.cage_corners      = []
        self.cage_handle_pos   = None
        self.current_cage_mode = "place_inf_ant"
        self.apply_cage_btn.config(state="disabled")
        self.show_status(
            f"Cage at {self.cage_level_var.get()} | Step 1/4: Click INFERIOR ANTERIOR corner",
            "info", persistent=True
        )
    
    # ─────────────────────────────────────────────────────────────────────────
    # Geometry helpers
    # ─────────────────────────────────────────────────────────────────────────
    
    def _cage_cut_ys(self):
        """(sup_cut_y, inf_cut_y) from current cage_corners."""
        ia, ip, sa, sp = self.cage_corners
        return int((sa[1] + sp[1]) / 2), int((ia[1] + ip[1]) / 2)
    
    def _cage_rotation_pil(self):
        """
        Returns the rotation angle in degrees (CW-positive in screen/image space).
        Negate before passing to PIL.Image.rotate(), which uses CCW-positive.
        """
        inf_ant, _, sup_ant, _ = self.cage_corners
        handle = self.cage_handle_pos
        a_orig = math.atan2(sup_ant[1] - inf_ant[1], sup_ant[0] - inf_ant[0])
        a_new  = math.atan2(handle[1]  - inf_ant[1], handle[0]  - inf_ant[0])
        return -math.degrees(a_new - a_orig)
    
    def _cage_paste_y(self, inf_cut_y, sup_cut_y):
        """
        Vertical offset at which to paste the rotated top crop so that the
        cage height matches the handle's Y position.
        """
        cage_height_px = max(0, inf_cut_y - int(self.cage_handle_pos[1]))
        return (inf_cut_y - cage_height_px) - sup_cut_y
    
    def _get_cage_dimensions(self):
        """Return dict with ant_height, post_height, lordosis, unit."""
        if len(self.cage_corners) < 4 or self.cage_handle_pos is None:
            return {"ant_height": 0, "post_height": 0, "lordosis": 0, "unit": ""}
    
        inf_ant, inf_post, sup_ant, sup_post = self.cage_corners
        rot   = self._cage_rotation_pil()
        cos_a = math.cos(math.radians(rot))
        sin_a = math.sin(math.radians(rot))
        px, py = inf_ant
    
        def rot_pt(pt):
            dx, dy = pt[0] - px, pt[1] - py
            return (px + dx * cos_a - dy * sin_a,
                    py + dx * sin_a + dy * cos_a)
    
        sup_cut_y, inf_cut_y = self._cage_cut_ys()
        paste_y = self._cage_paste_y(inf_cut_y, sup_cut_y)
    
        # Rotated superior corners (in rotated_top coords) + vertical paste offset
        new_sa = rot_pt(sup_ant)
        new_sp = rot_pt(sup_post)
        new_sa = (new_sa[0], new_sa[1] + paste_y)
        new_sp = (new_sp[0], new_sp[1] + paste_y)
    
        ps = self.pixel_spacing[1] if self.is_calibrated else 1.0
        ant_h  = round(abs(inf_ant[1]  - new_sa[1]) * ps, 1)
        post_h = round(abs(inf_post[1] - new_sp[1]) * ps, 1)
    
        inf_v  = (inf_post[0] - inf_ant[0], inf_post[1] - inf_ant[1])
        sup_v  = (new_sp[0]   - new_sa[0],  new_sp[1]   - new_sa[1])
        m1, m2 = math.hypot(*inf_v), math.hypot(*sup_v)
        if m1 > 0 and m2 > 0:
            cos_ang  = max(-1, min(1, (inf_v[0]*sup_v[0] + inf_v[1]*sup_v[1]) / (m1*m2)))
            lordosis = round(math.degrees(math.acos(cos_ang)), 1)
        else:
            lordosis = 0.0
    
        unit = " mm" if self.is_calibrated else " px"
        return {"ant_height": ant_h, "post_height": post_h,
                "lordosis": lordosis, "unit": unit}
    
    def _update_cage_readouts(self):
        """Refresh the three sidebar labels."""
        if not hasattr(self, "cage_ant_h_label"):
            return
        d = self._get_cage_dimensions()
        u = d["unit"]
        self.cage_ant_h_label.config(text=f"Ant height:  {d['ant_height']}{u}")
        self.cage_post_h_label.config(text=f"Post height: {d['post_height']}{u}")
        self.cage_lord_label.config(text=f"Lordosis:    {d['lordosis']}°")
    
    # ─────────────────────────────────────────────────────────────────────────
    # Image operations
    # ─────────────────────────────────────────────────────────────────────────
    
    def get_cage_preview_image(self):
        """
        Return a PIL image with the disc region removed and the top half
        repositioned according to cage_handle_pos.  Does NOT modify self.image.
        """
        from PIL import ImageDraw
        if len(self.cage_corners) < 4 or self.cage_handle_pos is None:
            return self.image
    
        img    = self.image
        bg     = int(self.get_background_color(np.array(img)))
        w, h   = img.size
        inf_ant = self.cage_corners[0]
    
        sup_cut_y, inf_cut_y = self._cage_cut_ys()
        rot     = self._cage_rotation_pil()
        paste_y = self._cage_paste_y(inf_cut_y, sup_cut_y)
    
        # Crop top part (rows 0 → sup_cut_y) and rotate around inf_ant
        top_crop    = img.crop((0, 0, w, sup_cut_y))
        rotated_top = top_crop.rotate(
            -rot,
            center=(inf_ant[0], inf_ant[1]),  # center may be below crop — PIL handles it
            expand=False,
            fillcolor=bg,
        )
    
        # Compose: rotated top at paste_y, disc region blank, bottom unchanged
        result = Image.new(img.mode, (w, h), bg)
        result.paste(rotated_top, (0, paste_y))
        result.paste(img.crop((0, inf_cut_y, w, h)), (0, inf_cut_y))
        return result
    
    def apply_single_cage_transform(self, img, landmarks, cage_data):
        """
        Permanently apply one cage transform to img and landmarks.
        Returns (new_img, new_landmarks).
        """
        from PIL import ImageDraw
        inf_ant   = cage_data["inf_ant"]
        sup_cut_y = cage_data["sup_cut_y"]
        inf_cut_y = cage_data["inf_cut_y"]
        rot       = cage_data["rotation_deg"]
        paste_y   = cage_data["paste_y"]
    
        bg   = int(self.get_background_color(np.array(img)))
        w, h = img.size
    
        top_crop    = img.crop((0, 0, w, sup_cut_y))
        rotated_top = top_crop.rotate(
            -rot, center=(inf_ant[0], inf_ant[1]),
            expand=False, fillcolor=bg,
        )
    
        result = Image.new(img.mode, (w, h), bg)
        result.paste(rotated_top, (0, paste_y))
        result.paste(img.crop((0, inf_cut_y, w, h)), (0, inf_cut_y))
    
        # Transform landmarks to match PIL's Y-down rotation
        cos_a = math.cos(math.radians(-rot))
        sin_a = math.sin(math.radians(-rot))
        px, py = inf_ant
        
        new_lm = {}
        for name, (lx, ly) in landmarks.items():
            if ly < sup_cut_y:               # top segment: rotate + vertical shift
                dx, dy  = lx - px, ly - py
                # CW rotation matrix (matches PIL positive angle in Y-down coords)
                rx = px + dx * cos_a + dy * sin_a
                ry = py - dx * sin_a + dy * cos_a
                new_lm[name] = (rx, ry + paste_y)
            else:                            # bottom: unchanged
                new_lm[name] = (lx, ly)
        return result, new_lm
    
    def _apply_all_transforms(self):
        """Reapply all osteotomies then all cages from the original image."""
        if not self.original_image:
            return
    
        if self.osteotomies:
            self.apply_all_osteotomies()     # resets to original then re-runs each
        else:
            self.image = self.original_image.copy()
            if hasattr(self, "original_landmarks_backup") and self.original_landmarks_backup:
                self.landmarks = dict(self.original_landmarks_backup)
    
        for cage in self.applied_cages:
            if cage.get("applied"):
                self.image, self.landmarks = self.apply_single_cage_transform(
                    self.image, self.landmarks, cage
                )
    
    # ─────────────────────────────────────────────────────────────────────────
    # Canvas overlay
    # ─────────────────────────────────────────────────────────────────────────
    
    def _draw_cage_indicators(self):
        """Draw corner markers, endplate lines, and cage outline on canvas."""
        self.canvas.delete("cage_indicator")
    
        if not self.cage_corners:
            return
    
        def sc(pt):
            return (pt[0] * self.zoom + self.offset[0],
                    pt[1] * self.zoom + self.offset[1])
    
        labels    = ["IA", "IP", "SA", "SP"]
        colors    = ["#00FF88", "#00FF88", "#FFFF66", "#FFFF66"]
        hw        = int(16 * self.zoom)  # endplate tick half-width, zoom-aware
    
        # Draw placed corners
        for i, pt in enumerate(self.cage_corners):
            sx, sy = sc(pt)
            self.canvas.create_oval(sx-5, sy-5, sx+5, sy+5,
                                    fill=colors[i], outline=colors[i],
                                    tags="cage_indicator")
            self.canvas.create_text(sx+8, sy, text=labels[i], fill=colors[i],
                                    font=("Arial", 8, "bold"), anchor="w",
                                    tags="cage_indicator")
    
        # Draw inferior endplate line once both inferior corners are placed
        if len(self.cage_corners) >= 2:
            x1, y1 = sc(self.cage_corners[0])
            x2, y2 = sc(self.cage_corners[1])
            self.canvas.create_line(x1, y1, x2, y2,
                                    fill="#00FF88", width=2, tags="cage_indicator")
    
        # Draw superior endplate line once all 4 are placed
        if len(self.cage_corners) == 4:
            x1, y1 = sc(self.cage_corners[2])
            x2, y2 = sc(self.cage_corners[3])
            self.canvas.create_line(x1, y1, x2, y2,
                                    fill="#FFFF66", width=2, tags="cage_indicator")
    
        # Draw live cage parallelogram during adjust / confirm
        if (len(self.cage_corners) == 4
                and self.cage_handle_pos is not None
                and self.current_cage_mode in ("adjust", "confirm")):
    
            inf_ant, inf_post, sup_ant, sup_post = self.cage_corners
            rot   = self._cage_rotation_pil()
            cos_a = math.cos(math.radians(rot))
            sin_a = math.sin(math.radians(rot))
            px, py = inf_ant
    
            sup_cut_y, inf_cut_y = self._cage_cut_ys()
            paste_y = self._cage_paste_y(inf_cut_y, sup_cut_y)
    
            def rot_and_shift(pt):
                dx, dy = pt[0] - px, pt[1] - py
                rx = px + dx * cos_a - dy * sin_a
                ry = py + dx * sin_a + dy * cos_a
                return sc((rx, ry + paste_y))
    
            new_sa = rot_and_shift(sup_ant)
            new_sp = rot_and_shift(sup_post)
            ia_sc  = sc(inf_ant)
            ip_sc  = sc(inf_post)
    
            # Cage body outline (dashed orange parallelogram)
            outline_color = "#FFD700" if self.current_cage_mode == "confirm" else "#FF9900"
            self.canvas.create_polygon(
                ia_sc[0], ia_sc[1],
                ip_sc[0], ip_sc[1],
                new_sp[0], new_sp[1],
                new_sa[0], new_sa[1],
                outline=outline_color, fill="", width=2,
                dash=(6, 4), tags="cage_indicator"
            )
            # Anterior column axis
            self.canvas.create_line(ia_sc[0], ia_sc[1], new_sa[0], new_sa[1],
                                    fill=outline_color, width=1,
                                    dash=(3, 6), tags="cage_indicator")
    
            # Dimension label at cage centre
            cx = (ia_sc[0] + ip_sc[0] + new_sa[0] + new_sp[0]) / 4
            cy = (ia_sc[1] + ip_sc[1] + new_sa[1] + new_sp[1]) / 4
            d  = self._get_cage_dimensions()
            u  = d["unit"]
            self.canvas.create_text(
                cx, cy,
                text=f"{d['ant_height']}{u}A / {d['post_height']}{u}P\n{d['lordosis']}°",
                fill=outline_color, font=("Arial", 9, "bold"),
                anchor="center", tags="cage_indicator"
            )
    
    # ─────────────────────────────────────────────────────────────────────────
    # Commit / delete / reset
    # ─────────────────────────────────────────────────────────────────────────
    
    def apply_cage(self):
        """Commit the current cage onto the applied_cages stack."""
        if (self.current_cage_mode not in ("confirm",)
                or len(self.cage_corners) != 4
                or self.cage_handle_pos is None):
            self.show_status("Complete cage placement first.", "error")
            return
    
        sup_cut_y, inf_cut_y = self._cage_cut_ys()
        rot     = self._cage_rotation_pil()
        paste_y = self._cage_paste_y(inf_cut_y, sup_cut_y)
        dims    = self._get_cage_dimensions()
        inf_ant, inf_post, sup_ant, sup_post = self.cage_corners
    
        cage_data = {
            "inf_ant":      inf_ant,
            "inf_post":     inf_post,
            "sup_ant":      sup_ant,
            "sup_post":     sup_post,
            "sup_cut_y":    sup_cut_y,
            "inf_cut_y":    inf_cut_y,
            "rotation_deg": rot,
            "paste_y":      paste_y,
            "handle_final": self.cage_handle_pos,
            "ant_height":   dims["ant_height"],
            "post_height":  dims["post_height"],
            "lordosis":     dims["lordosis"],
            "unit":         dims["unit"],
            "level":        self.cage_level_var.get(),
            "applied":      True,
        }
        self.applied_cages.append(cage_data)
    
        # Ensure original landmark backup exists
        if not hasattr(self, "original_landmarks_backup") or not self.original_landmarks_backup:
            self.original_landmarks_backup = dict(self.landmarks)
    
        self._apply_all_transforms()
    
        # Reset placement state
        self.current_cage_mode = None
        self.cage_corners      = []
        self.cage_handle_pos   = None
        self.end_persistent_instruction()
        self.apply_cage_btn.config(state="disabled")
        self.reset_cage_btn.config(state="normal")
    
        self.display_image()
        self.update_measurements(estimated=True)
        self.update_implant_summary()
    
        u = dims["unit"]
        self.show_status(
            f"Cage applied at {cage_data['level']}: "
            f"{dims['ant_height']}{u} ant / {dims['post_height']}{u} post / {dims['lordosis']}°",
            "success"
        )
    
    def delete_applied_cage(self, index):
        """Pop one cage from the stack and reapply the rest."""
        if 0 <= index < len(self.applied_cages):
            removed = self.applied_cages.pop(index)
            self._apply_all_transforms()
            self.display_image()
            self.update_measurements(estimated=True)
            self.update_implant_summary()
            self.show_status(f"Cage at {removed['level']} removed.", "info")
            if not self.applied_cages:
                self.reset_cage_btn.config(state="disabled")
    
    def reset_all_cages(self):
        """Remove all cage transforms and return to post-osteotomy state."""
        self.applied_cages     = []
        self.current_cage_mode = None
        self.cage_corners      = []
        self.cage_handle_pos   = None
    
        self.apply_cage_btn.config(state="disabled")
        self.reset_cage_btn.config(state="disabled")
        self.place_cage_btn.config(state="normal")
    
        if self.osteotomies:
            self.apply_all_osteotomies()
        else:
            self.reset_all_osteotomies()
    
        self.display_image()
        self.update_measurements()
        self.update_implant_summary()
        self.show_status("All cage transforms reset.", "info")
    

    def flip_image_horizontal(self):
        """Flip the image horizontally (left-right mirror)"""
        if self.image is None:
            messagebox.showwarning("Warning", "Please load an image first.")
            return
        
        # Flip the image
        self.image = self.image.transpose(Image.FLIP_LEFT_RIGHT)
        
        # Update all landmark positions to match the flipped image
        if self.landmarks:
            img_width = self.image.width
            for name, (x, y) in self.landmarks.items():
                # Mirror x-coordinate: new_x = img_width - old_x
                self.landmarks[name] = (img_width - x, y)
        
        # Update all screw positions
        if self.screws:
            img_width = self.image.width
            for screw in self.screws:
                head_x, head_y = screw["head"]
                tip_x, tip_y = screw["tip"]
                screw["head"] = (img_width - head_x, head_y)
                screw["tip"] = (img_width - tip_x, tip_y)
        
        # Update measurements and redraw
        self.update_measurements()
        self.display_image()
        self.show_status("Image flipped horizontally", "info")

    def setup_screw_tab(self):
        """Setup the existing screw placement interface"""
        screw_frame = tk.Frame(self.screw_tab, bg="lightgray")
        screw_frame.pack(pady=5, fill="x")
        
        # Screw parameters selection (keep existing functionality)
        params_frame = tk.Frame(screw_frame, bg="lightgray")
        params_frame.pack(fill="x", padx=5, pady=(10,0))
        
        # Vertebral Level
        tk.Label(params_frame, text="Level:", bg="lightgray").grid(row=0, column=0, sticky="w", padx=5)
        # DON'T redefine self.level_var if it already exists
        if not hasattr(self, 'level_var'):
            self.level_var = tk.StringVar(value="L4")
        self.level_dropdown = ttk.Combobox(params_frame, textvariable=self.level_var, width=8)
        self.level_dropdown['values'] = ('C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'C7',
                                         'T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8', 'T9', 'T10', 'T11', 'T12',
                                         'L1', 'L2', 'L3', 'L4', 'L5', 
                                         'S1', 'S2', 'Iliac')
        self.level_dropdown.grid(row=0, column=1, padx=5, pady=2)
        
        # Screw Diameter - DON'T redefine if it already exists
        tk.Label(params_frame, text="Diameter (mm):", bg="lightgray").grid(row=0, column=2, sticky="w", padx=5)
        if not hasattr(self, 'screw_diameter_var'):
            self.screw_diameter_var = tk.StringVar(value="6.0")
        self.screw_diameter_dropdown = ttk.Combobox(params_frame, textvariable=self.screw_diameter_var, width=8)
        self.screw_diameter_dropdown['values'] = ('4.5', '5.0', '5.5', '6.0', '6.5', '7.0', '7.5', '8.0')
        self.screw_diameter_dropdown.grid(row=0, column=3, padx=5, pady=2)
        
        # Instructions
        instructions_frame = tk.Frame(screw_frame, bg="lightgray")
        instructions_frame.pack(fill="x", padx=5, pady=5)
        
        tk.Label(instructions_frame, text="Custom Screw Placement:", bg="lightgray", font=("Arial", 9, "bold")).pack(anchor="w")
        instructions = (
            "1. Select vertebral level above\n"
            "2. Click 'Place Screw' button\n"
            "3. Click to set entry point (screw head)\n"
            "4. Click to set trajectory (screw tip)\n"
            "5. Control+Click to drag screw points for adjustment"
        )
        tk.Label(instructions_frame, text=instructions, bg="lightgray", justify="left", font=("Arial", 8)).pack(anchor="w", padx=10)
        
        self.place_screw_button = tk.Button(instructions_frame, text="Place Custom Screw", command=self.place_screw)
        self.place_screw_button.pack(pady=5)
    
    def setup_interbody_tab(self):
        """Setup interbody cage placement interface"""
        interbody_frame = tk.Frame(self.interbody_tab, bg="lightgray")
        interbody_frame.pack(pady=5, fill="x")
        
        tk.Label(interbody_frame, text="Interbody Cage Options:", bg="lightgray", font=("Arial", 10, "bold")).pack(anchor="w", padx=5)
        
        # Placement method selection
        method_frame = tk.Frame(interbody_frame, bg="lightgray")
        method_frame.pack(fill="x", padx=5, pady=5)
        
        self.interbody_method = tk.StringVar(value="draw")
        tk.Radiobutton(method_frame, text="Draw Custom Shape", variable=self.interbody_method, 
                       value="draw", bg="lightgray", command=self.update_interbody_options).pack(anchor="w")
        tk.Radiobutton(method_frame, text="Predefined Template (Drag & Drop)", variable=self.interbody_method, 
                       value="template", bg="lightgray", command=self.update_interbody_options).pack(anchor="w")
        
        # Parameters frame
        params_frame = tk.Frame(interbody_frame, bg="lightgray")
        params_frame.pack(fill="x", padx=5, pady=5)
        
        # Level selection
        tk.Label(params_frame, text="Level:", bg="lightgray").grid(row=0, column=0, sticky="w")
        self.interbody_level_var = tk.StringVar(value="L4-L5")
        level_combo = ttk.Combobox(params_frame, textvariable=self.interbody_level_var, width=10)
        level_combo['values'] = ('L1-L2', 'L2-L3', 'L3-L4', 'L4-L5', 'L5-S1')
        level_combo.grid(row=0, column=1, padx=5, pady=2)
        
        # Cage dimensions with validation
        tk.Label(params_frame, text="Width (mm):", bg="lightgray").grid(row=1, column=0, sticky="w")
        self.interbody_width_var = tk.StringVar(value="12")
        self.interbody_width_entry = tk.Entry(params_frame, textvariable=self.interbody_width_var, width=8)
        self.interbody_width_entry.grid(row=1, column=1, padx=5, pady=2)
        self.interbody_width_entry.bind('<FocusOut>', lambda e: self.validate_cage_input(self.interbody_width_var, 8, 18, 12))
        
        tk.Label(params_frame, text="Length (mm):", bg="lightgray").grid(row=2, column=0, sticky="w")
        self.interbody_length_var = tk.StringVar(value="28")
        self.interbody_length_entry = tk.Entry(params_frame, textvariable=self.interbody_length_var, width=8)
        self.interbody_length_entry.grid(row=2, column=1, padx=5, pady=2)
        self.interbody_length_entry.bind('<FocusOut>', lambda e: self.validate_cage_input(self.interbody_length_var, 20, 35, 28))
        
        tk.Label(params_frame, text="Height (mm):", bg="lightgray").grid(row=3, column=0, sticky="w")
        self.interbody_height_var = tk.StringVar(value="10")
        self.interbody_height_entry = tk.Entry(params_frame, textvariable=self.interbody_height_var, width=8)
        self.interbody_height_entry.grid(row=3, column=1, padx=5, pady=2)
        self.interbody_height_entry.bind('<FocusOut>', lambda e: self.validate_cage_input(self.interbody_height_var, 6, 16, 10))
        
        tk.Label(params_frame, text="Lordosis (°):", bg="lightgray").grid(row=4, column=0, sticky="w")
        self.interbody_lordosis_var = tk.StringVar(value="6")
        self.interbody_lordosis_entry = tk.Entry(params_frame, textvariable=self.interbody_lordosis_var, width=8)
        self.interbody_lordosis_entry.grid(row=4, column=1, padx=5, pady=2)
        self.interbody_lordosis_entry.bind('<FocusOut>', lambda e: self.validate_cage_input(self.interbody_lordosis_var, 0, 20, 6))
        
        # Instructions frames (will show/hide based on method)
        self.interbody_draw_frame = tk.Frame(interbody_frame, bg="lightgray")
        self.interbody_draw_frame.pack(fill="x", padx=5, pady=5)
        
        tk.Label(self.interbody_draw_frame, text="Draw Instructions:", bg="lightgray", font=("Arial", 9, "bold")).pack(anchor="w")
        draw_instructions = (
            "1. Click 'Place Interbody Cage' button\n"
            "2. Click 4 corners to define the cage shape:\n"
            "   - Left inferior endplate corner\n"
            "   - Right inferior endplate corner\n"
            "   - Left superior endplate corner\n"  
            "   - Right superior endplate corner\n"
            "3. Alt+Click and drag to reposition\n"
            "4. Shift+Click to reveal resize handles\n"
            "5. Move handles by dragging to resize\n"
            "6. Shift+Click to hide resize handles"
        )
        tk.Label(self.interbody_draw_frame, text=draw_instructions, bg="lightgray", justify="left", font=("Arial", 8)).pack(anchor="w", padx=10)
        
        self.interbody_template_frame = tk.Frame(interbody_frame, bg="lightgray")
        # Initially hidden
        
        tk.Label(self.interbody_template_frame, text="Template Instructions:", bg="lightgray", font=("Arial", 9, "bold")).pack(anchor="w")
        template_instructions = (
            "1. Click 'Place Template' button\n"
            "2. A predefined cage will appear\n"
            "3. Alt+Click and drag to reposition\n"
            "4. Shift+Click to show resize handles\n"
            "5. Drag corner handles to resize"
        )
        tk.Label(self.interbody_template_frame, text=template_instructions, bg="lightgray", justify="left", font=("Arial", 8)).pack(anchor="w", padx=10)
        
        # Place button
        self.place_interbody_button = tk.Button(interbody_frame, text="Place Interbody Cage", 
                                               command=self.place_interbody_cage)
        self.place_interbody_button.pack(pady=5)
    
    def on_mouse_motion(self, event):
        """Show tooltips when hovering over interactive elements"""
        # ── Cage live preview ─────────────────────────────────────────────────
        if self.current_cage_mode == "adjust" and len(self.cage_corners) == 4:
            self.cage_handle_pos = (
                (event.x - self.offset[0]) / self.zoom,
                (event.y - self.offset[1]) / self.zoom,
            )
            self._update_cage_readouts()
            self.display_image()
            return

        x = (event.x - self.offset[0]) / self.zoom
        y = (event.y - self.offset[1]) / self.zoom
        
        # Check if hovering over a cage
        for cage in self.cages:
            if self.point_in_quad(x, y, cage["corners"]):
                self.status_label.config(text="Alt+drag to move | Shift+click for resize handles")
                return
        
        # Clear status if not hovering over anything special
        self.status_label.config(text="")
    
    def setup_corpectomy_tab(self):
        """Setup corpectomy cage placement interface"""
        corpectomy_frame = tk.Frame(self.corpectomy_tab, bg="lightgray")
        corpectomy_frame.pack(pady=5, fill="x")
        
        tk.Label(corpectomy_frame, text="Corpectomy Cage Options:", bg="lightgray", font=("Arial", 10, "bold")).pack(anchor="w", padx=5)
        
        # Placement method selection
        method_frame = tk.Frame(corpectomy_frame, bg="lightgray")
        method_frame.pack(fill="x", padx=5, pady=5)
        
        self.corpectomy_method = tk.StringVar(value="draw")
        tk.Radiobutton(method_frame, text="Draw Custom Shape", variable=self.corpectomy_method, 
                       value="draw", bg="lightgray", command=self.update_corpectomy_options).pack(anchor="w")
        tk.Radiobutton(method_frame, text="Cylindrical Template (Drag & Drop)", variable=self.corpectomy_method, 
                       value="template", bg="lightgray", command=self.update_corpectomy_options).pack(anchor="w")
        
        # Parameters frame
        params_frame = tk.Frame(corpectomy_frame, bg="lightgray")
        params_frame.pack(fill="x", padx=5, pady=5)
        
        # Level selection
        tk.Label(params_frame, text="Vertebra Removed:", bg="lightgray").grid(row=0, column=0, sticky="w")
        self.corpectomy_level_var = tk.StringVar(value="L3")
        level_combo = ttk.Combobox(params_frame, textvariable=self.corpectomy_level_var, width=10)
        level_combo['values'] = ('T10', 'T11', 'T12', 'L1', 'L2', 'L3', 'L4', 'L5')
        level_combo.grid(row=0, column=1, padx=5, pady=2)
        
        # Cage dimensions with validation
        tk.Label(params_frame, text="Diameter (mm):", bg="lightgray").grid(row=1, column=0, sticky="w")
        self.corpectomy_diameter_var = tk.StringVar(value="22")
        self.corpectomy_diameter_entry = tk.Entry(params_frame, textvariable=self.corpectomy_diameter_var, width=8)
        self.corpectomy_diameter_entry.grid(row=1, column=1, padx=5, pady=2)
        self.corpectomy_diameter_entry.bind('<FocusOut>', lambda e: self.validate_cage_input(self.corpectomy_diameter_var, 16, 30, 22))
        
        tk.Label(params_frame, text="Height (mm):", bg="lightgray").grid(row=2, column=0, sticky="w")
        self.corpectomy_height_var = tk.StringVar(value="50")
        self.corpectomy_height_entry = tk.Entry(params_frame, textvariable=self.corpectomy_height_var, width=8)
        self.corpectomy_height_entry.grid(row=2, column=1, padx=5, pady=2)
        self.corpectomy_height_entry.bind('<FocusOut>', lambda e: self.validate_cage_input(self.corpectomy_height_var, 30, 80, 50))
        
        # Instructions
        instructions_frame = tk.Frame(corpectomy_frame, bg="lightgray")
        instructions_frame.pack(fill="x", padx=5, pady=5)
        
        instructions = (
            "Corpectomy cage replaces a removed vertebral body.\n"
            "Draw mode: Click to define cage boundaries\n"
            "Template mode: Place pre-sized cage into position\n"
            "Alt+Click and drag to reposition"
        )
        tk.Label(instructions_frame, text=instructions, bg="lightgray", justify="left", font=("Arial", 8)).pack(anchor="w", padx=10)
        
        # Place button
        self.place_corpectomy_button = tk.Button(corpectomy_frame, text="Place Corpectomy Cage", 
                                                command=self.place_corpectomy_cage)
        self.place_corpectomy_button.pack(pady=5)
    
    def validate_cage_input(self, var, min_val, max_val, default):
        """Validate numeric input for cage dimensions"""
        try:
            value = float(var.get())
            if value < min_val or value > max_val:
                self.show_status(f"Value must be between {min_val} and {max_val} mm. Reset to default.", "warning")
                var.set(str(default))
        except ValueError:
            self.show_status(f"Invalid input. Please enter a number between {min_val} and {max_val}.", "error")
            var.set(str(default))
    
    def update_interbody_options(self):
        """Show/hide relevant options based on interbody placement method"""
        if self.interbody_method.get() == "draw":
            self.interbody_draw_frame.pack(fill="x", padx=5, pady=5)
            self.interbody_template_frame.pack_forget()
        else:
            self.interbody_draw_frame.pack_forget()
            self.interbody_template_frame.pack(fill="x", padx=5, pady=5)
    
    def update_corpectomy_options(self):
        """Show/hide relevant options based on corpectomy placement method"""
        # Similar implementation if needed
        pass
    
    def place_interbody_cage(self):
        """Begin placing an interbody cage"""
        if self.interbody_method.get() == "draw":
            self.current_cage_type = "interbody_draw"
            self.cage_points = []
            level = self.interbody_level_var.get()
            self.show_status(f"Click 4 points to define interbody cage at {level}", "info", persistent=True)
        else:
            # Template placement - create a predefined cage at cursor
            self.current_cage_type = "interbody_template"
            self.show_status("Click to place interbody cage template", "info")
    
    def place_corpectomy_cage(self):
        """Begin placing a corpectomy cage"""
        if self.corpectomy_method.get() == "draw":
            self.current_cage_type = "corpectomy_draw"
            self.cage_points = []
            level = self.corpectomy_level_var.get()
            self.show_status(f"Click 2 points to define corpectomy cage height at {level}", "info", persistent=True)
        else:
            # Template placement
            self.current_cage_type = "corpectomy_template"
            self.show_status("Click to place corpectomy cage template", "info")

    # Add this method to update calibration status display:
    def update_calibration_status(self):
        if self.is_calibrated:
            angle_text = ""
            if self.calibration_angle is not None:
                angle_text = f" | Line: {self.calibration_angle:.1f}°"
            self.calib_status.config(text=f"Calibrated: {self.pixel_spacing[0]:.3f} mm/pixel{angle_text}", 
                                    bg="lightgreen", fg="black")
        else:
            self.calib_status.config(text="Not calibrated - measurements in pixels", 
                                    bg="lightcoral", fg="white")

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
    
    def select_cage_for_resize(self, event):
        """Select a cage to show resize handles"""
        x = (event.x - self.offset[0]) / self.zoom
        y = (event.y - self.offset[1]) / self.zoom
        
        # Clear any existing handles
        self.clear_cage_handles()
        
        # Find which cage was clicked
        for i, cage in enumerate(self.cages):
            if self.point_in_quad(x, y, cage["corners"]):
                self.create_cage_handles(i)
                self.show_status("Drag corner handles to resize cage", "info")
                return
    
    def handle_cage_interaction(self, event):
        """Unified handler for cage interactions"""
        # Check if clicking on a handle first
        item = self.canvas.find_closest(event.x, event.y)
        if item:
            tags = self.canvas.gettags(item[0])
            if "cage_handle" in tags:
                self.start_resize_cage(event)
                return
    
    def handle_cage_drag_or_resize(self, event):
        """Handle either resize or other drag operations"""
        if self.resizing_cage:
            self.on_resize_cage(event)
    
    def handle_cage_release(self, event):
        """Handle release for cage operations"""
        if self.resizing_cage:
            self.stop_resize_cage(event)
    
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
            
    def update_file_path_display(self):
        """Update the file path display to show the currently loaded file"""
        if self.current_file_path:
            # Extract just the filename and directory for display
            file_name = os.path.basename(self.current_file_path)
            directory = os.path.dirname(self.current_file_path)
            
            # Get available width (approximate characters that can fit)
            # Estimate based on font and widget width
            max_chars_per_line = 100  # Adjust this value based on your sidebar width
            
            # Smart truncation for directory path
            if len(directory) > max_chars_per_line:
                # Split path and keep the most relevant parts
                path_parts = directory.split(os.sep)
                if len(path_parts) > 3:
                    # Keep drive/root and last 2 directories
                    truncated_dir = os.sep.join([path_parts[0], "...", path_parts[-2], path_parts[-1]])
                else:
                    # Simple truncation from the beginning
                    truncated_dir = "..." + directory[-(max_chars_per_line-3):]
                directory = truncated_dir
                
            display_text = f"📁 {directory}\n📄 {file_name}"
            self.file_path_label.config(text=display_text, fg="darkblue")
        else:
            self.file_path_label.config(text="No file loaded", fg="gray")
    
    def load_image(self):
        try:
            filepath = filedialog.askopenfilename(
                filetypes=[
                    ("All supported", "*.dcm;*.jpg;*.jpeg;*.png"),
                    ("DICOM files", "*.dcm"), 
                    ("JPEG files", "*.jpg;*.jpeg"),
                    ("PNG files", "*.png")
                ]
            )
            self.current_file_path = filepath
            self.update_file_path_display()
            if not filepath:
                return
            
            file_ext = filepath.lower().split('.')[-1]
            
            if file_ext == 'dcm':
                # DICOM handling (existing logic)
                self.ds = pydicom.dcmread(filepath)
                pixel_array = self.ds.pixel_array.astype(np.float32)
                norm_img = ((pixel_array - np.min(pixel_array)) / np.ptp(pixel_array) * 255).astype(np.uint8)
                self.original_image = Image.fromarray(norm_img)
                
                # Extract pixel spacing
                if hasattr(self.ds, 'PixelSpacing'):
                    spacing = self.ds.PixelSpacing
                    self.pixel_spacing = [float(spacing[0]), float(spacing[1])]
                    self.is_calibrated = True
                else:
                    self.pixel_spacing = [1.0, 1.0]
                    self.is_calibrated = False
                    messagebox.showwarning("Warning", "No pixel spacing found in DICOM. Please calibrate the image.")
            
            elif file_ext in ['jpg', 'jpeg', 'png']:
                # Handle JPEG/PNG files
                self.original_image = Image.open(filepath)
                if self.original_image.mode != 'L':  # Convert to grayscale if not already
                    self.original_image = self.original_image.convert('L')
                
                # No calibration data available for JPEG/PNG
                self.pixel_spacing = [1.0, 1.0]  # Default values
                self.is_calibrated = False
                self.ds = None
                messagebox.showinfo("Calibration Required", 
                                  "Please calibrate the image using two known points.\nClick 'Calibrate Image' button.")
            
            self.image = self.original_image
            
            # Reset zoom and position for new image
            self.zoom = 0.1
            self.offset = [0, 0]
            
            # Clear existing landmarks and measurements
            self.landmarks = {}
            self.label_offsets = {}
            self.label_anchor_points = {}
            self.update_measurements()
            
            self.display_image()
            self.info_label.config(text="Image loaded successfully. " + 
                                 ("Calibrate first!" if not self.is_calibrated else "Place landmarks."))
            
            self.update_calibration_status()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load image file: {str(e)}")
    
    def update_image_enhancement(self, val=None):
        """Update both brightness and contrast of the image"""
        if self.original_image is None:
            return
        
        # Get current values
        brightness_val = self.brightness_slider.get()
        contrast_val = self.contrast_slider.get()
        
        # Apply brightness first, then contrast
        brightness_enhancer = ImageEnhance.Brightness(self.original_image)
        temp_image = brightness_enhancer.enhance(brightness_val)
        
        contrast_enhancer = ImageEnhance.Contrast(temp_image)
        self.image = contrast_enhancer.enhance(contrast_val)
        
        self.display_image()
    
    def reset_image_enhancement(self):
        """Reset brightness and contrast to default values"""
        if self.original_image is None:
            return
        
        # Reset sliders to default values
        self.brightness_slider.set(1.0)
        self.contrast_slider.set(1.0)
        
        # Reset image to original
        self.image = self.original_image.copy()
        self.display_image()
        
        self.show_status("Image enhancement reset to defaults", "info")
        
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
        if hasattr(self, 'implant_list_frame'):
            self.update_implant_summary()
        
        try:
            # Use live composite image during cage preview, otherwise self.image
            if self.current_cage_mode == "preview" and self.cage_bottom_pt and self.cage_top_current:
                img_to_show = self.get_cage_preview_image()
            else:
                img_to_show = self.image

            if (self.current_cage_mode in ("adjust", "confirm")
                    and len(self.cage_corners) == 4
                    and self.cage_handle_pos is not None):
                img_to_show = self.get_cage_preview_image()
            else:
                img_to_show = self.image

            resized = img_to_show.resize(
                (int(img_to_show.width * self.zoom), int(img_to_show.height * self.zoom))
            )
            
            self.tk_image = ImageTk.PhotoImage(resized)
            self.canvas.delete("all")
            self.canvas.create_image(self.offset[0], self.offset[1], anchor="nw", image=self.tk_image)

            # Draw cage placement indicators (INF/SUP lines + dashed outline)
            self.canvas.delete("cage_indicator")
            if self.cage_bottom_pt:
                def sc(pt):
                    return (pt[0] * self.zoom + self.offset[0],
                            pt[1] * self.zoom + self.offset[1])
                bx, by = sc(self.cage_bottom_pt)
                hw = 18
                self.canvas.create_line(bx-hw, by, bx+hw, by, fill="#00FF88", width=3, tags="cage_indicator")
                self.canvas.create_oval(bx-5, by-5, bx+5, by+5, fill="#00FF88", outline="#00FF88", tags="cage_indicator")
                self.canvas.create_text(bx+hw+6, by, text="INF", fill="#00FF88", font=("Arial", 8, "bold"), anchor="w", tags="cage_indicator")
                if self.cage_top_current:
                    tx, ty = sc(self.cage_top_current)
                    sup_color = "#FFD700" if self.current_cage_mode == "confirm" else "#FFFF66"
                    self.canvas.create_line(tx-hw, ty, tx+hw, ty, fill=sup_color, width=3, tags="cage_indicator")
                    self.canvas.create_oval(tx-5, ty-5, tx+5, ty+5, fill=sup_color, outline=sup_color, tags="cage_indicator")
                    self.canvas.create_text(tx+hw+6, ty, text="SUP", fill=sup_color, font=("Arial", 8, "bold"), anchor="w", tags="cage_indicator")
                    self.canvas.create_polygon(bx-hw, by, bx+hw, by, tx+hw, ty, tx-hw, ty,
                                               outline="#FF9900", fill="", width=2, dash=(6, 4), tags="cage_indicator")
                    self.canvas.create_line(bx, by, tx, ty, fill="#FF9900", width=1, dash=(3, 6), tags="cage_indicator")

            self._draw_cage_indicators()            
            self.draw_calibration_line()
            self.draw_landmarks()
            self.draw_implants()
            self.draw_osteotomy()
            self.draw_measurements()
            if self.rod_line:
                self.draw_rod()
            self.draw_connecting_lines()  # Add connecting lines after drawing labels
        except Exception as e:
            messagebox.showerror("Error", f"Display error: {str(e)}")
    
    def on_click(self, event):
        if self.image is None:
            return
        
        # Convert from canvas coordinates to image coordinates
        x = int((event.x - self.offset[0]) / self.zoom)
        y = int((event.y - self.offset[1]) / self.zoom)
        
        # Check if coordinates are within image boundaries
        if not (0 <= x < self.image.width and 0 <= y < self.image.height):
            return
        
        # Handle calibration mode
        if self.calibration_mode:
            self.calibration_points.append((x, y))
            
            if len(self.calibration_points) == 1:
                self.info_label.config(text="Calibration: Click second point")
            elif len(self.calibration_points) == 2:
                # Draw calibration line
                p1_canvas = (self.calibration_points[0][0] * self.zoom + self.offset[0],
                            self.calibration_points[0][1] * self.zoom + self.offset[1])
                p2_canvas = (self.calibration_points[1][0] * self.zoom + self.offset[0],
                            self.calibration_points[1][1] * self.zoom + self.offset[1])
                
                if self.calibration_line_id:
                    self.canvas.delete(self.calibration_line_id)
                
                self.calibration_line_id = self.canvas.create_line(
                    p1_canvas[0], p1_canvas[1], p2_canvas[0], p2_canvas[1],
                    fill='lime', width=3, tags="calibration"
                )
                
                # Show distance in pixels
                pixel_dist = math.sqrt((self.calibration_points[1][0] - self.calibration_points[0][0])**2 + 
                                     (self.calibration_points[1][1] - self.calibration_points[0][1])**2)
                self.info_label.config(text=f"Distance: {pixel_dist:.1f} pixels. Enter real distance.")
                
                self.finish_calibration()
            return
        
        if self.current_measurement_tool is not None:
            x = int((event.x - self.offset[0]) / self.zoom)
            y = int((event.y - self.offset[1]) / self.zoom)
            self.add_measurement_point(x, y)
            return
        
        # Handle landmark placement (your existing logic)
        if self.current_landmark_name:
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
                    "corners": self.cage_points.copy(),  # <-- FIXED: using cage_points instead
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
                
        elif self.current_cage_mode is not None:
            x = int((event.x - self.offset[0]) / self.zoom)
            y = int((event.y - self.offset[1]) / self.zoom)

            if self.current_cage_mode in (
                    "place_inf_ant", "place_inf_post",
                    "place_sup_ant",  "place_sup_post"):

                self.cage_corners.append((x, y))

                if self.current_cage_mode == "place_inf_ant":
                    self.current_cage_mode = "place_inf_post"
                    self.show_status("Step 2/4: Click INFERIOR POSTERIOR corner", "info", persistent=True)

                elif self.current_cage_mode == "place_inf_post":
                    self.current_cage_mode = "place_sup_ant"
                    self.show_status("Step 3/4: Click SUPERIOR ANTERIOR corner", "info", persistent=True)

                elif self.current_cage_mode == "place_sup_ant":
                    self.current_cage_mode = "place_sup_post"
                    self.show_status("Step 4/4: Click SUPERIOR POSTERIOR corner", "info", persistent=True)

                elif self.current_cage_mode == "place_sup_post":
                    # All 4 corners placed → enter live adjustment
                    self.current_cage_mode = "adjust"
                    self.cage_handle_pos   = self.cage_corners[2]  # start at sup_ant
                    self.end_persistent_instruction()
                    self.show_status(
                        "Move cursor to adjust height & lordosis — click to lock",
                        "info", persistent=True
                    )

                self.display_image()

            elif self.current_cage_mode == "adjust":
                # Lock current position
                self.current_cage_mode = "confirm"
                self.end_persistent_instruction()
                self._update_cage_readouts()
                dims = self._get_cage_dimensions()
                u    = dims["unit"]
                self.show_status(
                    f"Cage locked — {dims['ant_height']}{u} ant / "
                    f"{dims['post_height']}{u} post / {dims['lordosis']}° — click Apply",
                    "success"
                )
                self.apply_cage_btn.config(state="normal")
                self.display_image()

            elif self.current_cage_mode == "confirm":
                # Re-click in confirm → go back to adjust for fine-tuning
                self.current_cage_mode = "adjust"
                self.show_status("Move cursor to re-adjust — click to lock again", "info", persistent=True)
                self.display_image()
                
        elif self.current_osteotomy == "placing_wedge":
            x = int((event.x - self.offset[0]) / self.zoom)
            y = int((event.y - self.offset[1]) / self.zoom)
            
            self.current_osteotomy_points.append((x, y))
            
            # Update instructions based on progress
            level = self.osteotomy_level_var.get()
            if len(self.current_osteotomy_points) == 1:
                self.show_status(f"Click superior posterior point at {level}", "info", persistent=True)
            elif len(self.current_osteotomy_points) == 2:
                self.show_status(f"Click inferior posterior point at {level}", "info", persistent=True)
            elif len(self.current_osteotomy_points) == 3:
                angle = self.calculate_wedge_angle(self.current_osteotomy_points)
                self.correction_label.config(text=f"Wedge angle: {angle:.1f}° - Ready to apply")
                self.apply_osteotomy_button.config(state="normal")
                self.current_osteotomy = None
                self.end_persistent_instruction()
                self.show_status(f"Osteotomy wedge defined: {angle:.1f}° at {level}", "success")
            
            self.display_image()
                
            
        # Handle cage placement
        elif self.current_cage_type:
            x = int((event.x - self.offset[0]) / self.zoom)
            y = int((event.y - self.offset[1]) / self.zoom)
            
            if self.current_cage_type == "interbody_draw":
                self.cage_points.append((x, y))
                self.display_image()
                
                # Update instructions
                if len(self.cage_points) == 1:
                    self.show_status("Click right inferior endplate corner", "info", persistent=True)
                elif len(self.cage_points) == 2:
                    self.show_status("Click left superior endplate corner", "info", persistent=True)
                elif len(self.cage_points) == 3:
                    self.show_status("Click right superior endplate corner", "info", persistent=True)
                elif len(self.cage_points) == 4:
                    # Calculate actual cage dimensions from drawn points
                    points = self.cage_points
                    
                    # Calculate width (average of top and bottom widths)
                    bottom_width = math.sqrt((points[1][0] - points[0][0])**2 + 
                                             (points[1][1] - points[0][1])**2) * self.pixel_spacing[0]
                    top_width = math.sqrt((points[3][0] - points[2][0])**2 + 
                                          (points[3][1] - points[2][1])**2) * self.pixel_spacing[0]
                    width = (bottom_width + top_width) / 2
                    
                    # Calculate height (average of left and right heights)
                    left_height = math.sqrt((points[2][0] - points[0][0])**2 + 
                                            (points[2][1] - points[0][1])**2) * self.pixel_spacing[1]
                    right_height = math.sqrt((points[3][0] - points[1][0])**2 + 
                                             (points[3][1] - points[1][1])**2) * self.pixel_spacing[1]
                    height = (left_height + right_height) / 2
                    
                    # Calculate lordosis angle from the difference in heights
                    lordosis = math.degrees(math.atan2(abs(top_width - bottom_width), height))
                    
                    # Use calculated values, but keep user's length specification
                    length = float(self.interbody_length_var.get())
                    level = self.interbody_level_var.get()
                    
                    self.cages.append({
                        "corners": self.cage_points.copy(),
                        "width": round(width, 1),
                        "length": length,  # Keep user specified
                        "height": round(height, 1),
                        "lordosis": round(lordosis, 1),
                        "level": level,
                        "type": "interbody"
                    })
                    
                    self.cage_points = []
                    self.current_cage_type = None
                    self.end_persistent_instruction()
                    self.show_status(f"Interbody cage placed at {level} - Measured: {width:.1f}×{length}×{height:.1f}mm with {lordosis:.1f}° lordosis", "success")
                    self.display_image()
                    self.update_implant_summary()
                    
            elif self.current_cage_type == "interbody_template":
                # Place a template cage at click position
                width = float(self.interbody_width_var.get())
                length = float(self.interbody_length_var.get())
                height = float(self.interbody_height_var.get())
                lordosis = float(self.interbody_lordosis_var.get())
                level = self.interbody_level_var.get()
                
                # Create a rectangular template centered at click point
                half_width = int(width / self.pixel_spacing[0] / 2)
                half_height = int(height / self.pixel_spacing[1] / 2)
                
                corners = [
                    (x - half_width, y + half_height),  # Bottom left
                    (x + half_width, y + half_height),  # Bottom right
                    (x - half_width, y - half_height),  # Top left
                    (x + half_width, y - half_height),  # Top right
                ]
                
                self.cages.append({
                    "corners": corners,
                    "width": width,
                    "length": length,
                    "height": height,
                    "lordosis": lordosis,
                    "level": level,
                    "type": "interbody"
                })
                
                self.current_cage_type = None
                self.show_status(f"Interbody cage template placed at {level}", "success")
                self.display_image()
                self.update_implant_summary()
                
            elif self.current_cage_type == "corpectomy_draw":
                self.cage_points.append((x, y))
                self.display_image()
                
                if len(self.cage_points) == 1:
                    self.show_status("Click to set corpectomy cage bottom", "info", persistent=True)
                elif len(self.cage_points) == 2:
                    # Create corpectomy cage
                    diameter = float(self.corpectomy_diameter_var.get())
                    height = float(self.corpectomy_height_var.get())
                    level = self.corpectomy_level_var.get()
                    
                    self.corpectomy_cages.append({
                        "top": self.cage_points[0],
                        "bottom": self.cage_points[1],
                        "diameter": diameter,
                        "height": height,
                        "level": level,
                        "type": "corpectomy"
                    })
                    
                    self.cage_points = []
                    self.current_cage_type = None
                    self.end_persistent_instruction()
                    self.show_status(f"Corpectomy cage placed at {level}", "success")
                    self.display_image()
                    self.update_implant_summary()
                    
            elif self.current_cage_type == "corpectomy_template":
                # Place a cylindrical template at click position
                diameter = float(self.corpectomy_diameter_var.get())
                height = float(self.corpectomy_height_var.get())
                level = self.corpectomy_level_var.get()
                
                # Create cylindrical cage centered at click
                radius_px = int(diameter / self.pixel_spacing[0] / 2)
                height_px = int(height / self.pixel_spacing[1])
                
                self.corpectomy_cages.append({
                    "center": (x, y),
                    "radius": radius_px,
                    "height": height_px,
                    "diameter": diameter,
                    "height_mm": height,
                    "level": level,
                    "type": "corpectomy_template"
                })
                
                self.current_cage_type = None
                self.show_status(f"Corpectomy cage template placed at {level}", "success")
                self.display_image()
                self.update_implant_summary()
            
        elif self.current_screw == "placing":
            x = int((event.x - self.offset[0]) / self.zoom)
            y = int((event.y - self.offset[1]) / self.zoom)
            
            # First click for screw head
            if len(self.osteotomy_points) == 0:
                self.osteotomy_points.append((x, y))
                self.show_status(f"Click to set screw tip/trajectory", "info", persistent=True)
                self.display_image()
            else:
                # Second click for screw tip
                head_x, head_y = self.osteotomy_points[0]
                tip_x, tip_y = x, y
                
                # Calculate screw length in mm
                length = math.sqrt((tip_x - head_x)**2 + (tip_y - head_y)**2) * self.pixel_spacing[0]
                length = round(length)  # Round to nearest mm
                
                # Use manually selected diameter
                diameter = float(self.screw_diameter_var.get())
                
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
                
    def setup_measurements_tab(self):
        """Setup the measurements display and controls"""
        measurements_frame = tk.Frame(self.measurements_tab, bg="lightgray")
        measurements_frame.pack(pady=5, fill="both", expand=True)
        
        tk.Label(measurements_frame, text="Active Measurements:", bg="lightgray", 
                 font=("Arial", 10, "bold")).pack(anchor="w", padx=5)
        
        # Scrollable frame for measurements list
        canvas = tk.Canvas(measurements_frame, bg="white", height=200)
        scrollbar = ttk.Scrollbar(measurements_frame, orient="vertical", command=canvas.yview)
        self.measurements_list_frame = tk.Frame(canvas, bg="white")
        
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        
        canvas.pack(side="left", fill="both", expand=True, padx=5)
        scrollbar.pack(side="right", fill="y")
        canvas.create_window((0, 0), window=self.measurements_list_frame, anchor="nw")
        
        # Clear all measurements button
        clear_btn = tk.Button(measurements_frame, text="Clear All Measurements",
                             command=self.clear_all_measurements, bg="red", fg="white")
        clear_btn.pack(pady=5)
    
    def start_measurement_tool(self, tool_type):
        """Start a measurement tool (length or angle)"""
        self.current_measurement_tool = tool_type
        self.measurement_points = []
        
        if tool_type == "length":
            self.show_status("Click two points to measure distance", "info", persistent=True)
        elif tool_type == "angle":
            self.show_status("Click three points to measure angle", "info", persistent=True)
    
    def add_measurement_point(self, x, y):
        """Add a point for the current measurement tool"""
        if self.current_measurement_tool is None:
            return
        
        self.measurement_points.append((x, y))
        
        if self.current_measurement_tool == "length" and len(self.measurement_points) == 2:
            self.complete_length_measurement()
        elif self.current_measurement_tool == "angle" and len(self.measurement_points) == 3:
            self.complete_angle_measurement()
        
        self.display_image()
    
    def complete_length_measurement(self):
        """Complete a length measurement"""
        if len(self.measurement_points) != 2:
            return
        
        p1, p2 = self.measurement_points
        distance = math.sqrt((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2) * self.pixel_spacing[0]
        
        measurement = {
            "type": "length",
            "points": self.measurement_points.copy(),
            "value": distance,
            "label": f"Length: {distance:.1f}mm"
        }
        
        self.measurements.append(measurement)
        self.current_measurement_tool = None
        self.measurement_points = []
        self.end_persistent_instruction()
        self.show_status(f"Length measurement: {distance:.1f}mm", "success")
        self.update_measurements_display()
    
    def complete_angle_measurement(self):
        """Complete an angle measurement"""
        if len(self.measurement_points) != 3:
            return
        
        p1, p2, p3 = self.measurement_points
        
        # Calculate angle using vectors
        v1 = (p1[0] - p2[0], p1[1] - p2[1])  # Vector from p2 to p1
        v2 = (p3[0] - p2[0], p3[1] - p2[1])  # Vector from p2 to p3
        
        # Calculate angle between vectors
        dot_product = v1[0] * v2[0] + v1[1] * v2[1]
        mag1 = math.sqrt(v1[0]**2 + v1[1]**2)
        mag2 = math.sqrt(v2[0]**2 + v2[1]**2)
        
        if mag1 == 0 or mag2 == 0:
            angle = 0
        else:
            cos_angle = dot_product / (mag1 * mag2)
            cos_angle = max(-1, min(1, cos_angle))  # Clamp to [-1, 1]
            angle = math.degrees(math.acos(cos_angle))
        
        measurement = {
            "type": "angle", 
            "points": self.measurement_points.copy(),
            "value": angle,
            "label": f"Angle: {angle:.1f}°"
        }
        
        self.measurements.append(measurement)
        self.current_measurement_tool = None
        self.measurement_points = []
        self.end_persistent_instruction()
        self.show_status(f"Angle measurement: {angle:.1f}°", "success")
        self.update_measurements_display()
    
    def update_measurements_display(self):
        """Update the measurements list in the measurements tab"""
        # Clear existing widgets
        for widget in self.measurements_list_frame.winfo_children():
            widget.destroy()
        
        for i, measurement in enumerate(self.measurements):
            meas_frame = tk.Frame(self.measurements_list_frame, bg="white")
            meas_frame.pack(fill="x", pady=1)
            
            tk.Label(meas_frame, text=f"{i+1}. {measurement['label']}", 
                    bg="white").pack(side="left")
            
            # Delete button
            tk.Button(meas_frame, text="×", 
                     command=lambda idx=i: self.delete_measurement(idx),
                     bg="white", fg="red", bd=0, font=("Arial", 9, "bold")).pack(side="right")
    
    def delete_measurement(self, index):
        """Delete a measurement"""
        if 0 <= index < len(self.measurements):
            del self.measurements[index]
            self.update_measurements_display()
            self.display_image()
            self.show_status(f"Measurement {index+1} deleted", "info")
    
    def clear_all_measurements(self):
        """Clear all measurements"""
        self.measurements = []
        self.update_measurements_display()
        self.display_image()
        self.show_status("All measurements cleared", "info")
    
    def start_drag_measurement(self, event):
        """Check if clicking on a measurement point to drag it"""
        if self.image is None:
            return
        
        # Convert click position to image coordinates
        x = (event.x - self.offset[0]) / self.zoom
        y = (event.y - self.offset[1]) / self.zoom
        
        # Check if we're near any measurement point
        threshold = 10 / self.zoom  # 10 pixels threshold, adjusted for zoom
        
        for i, measurement in enumerate(self.measurements):
            for j, point in enumerate(measurement["points"]):
                if math.sqrt((x - point[0])**2 + (y - point[1])**2) < threshold:
                    self.dragging_measurement = i
                    self.dragging_measurement_point = j
                    self.measurement_drag_start = (event.x, event.y)
                    self.canvas.config(cursor="fleur")
                    return
    
    def on_drag_measurement(self, event):
        """Drag a measurement point to new position"""
        if self.dragging_measurement is None or self.measurement_drag_start is None:
            return
        
        # Calculate movement in image coordinates
        dx = (event.x - self.measurement_drag_start[0]) / self.zoom
        dy = (event.y - self.measurement_drag_start[1]) / self.zoom
        
        # Update measurement point position
        measurement = self.measurements[self.dragging_measurement]
        old_x, old_y = measurement["points"][self.dragging_measurement_point]
        measurement["points"][self.dragging_measurement_point] = (old_x + dx, old_y + dy)
        
        # Recalculate measurement value
        if measurement["type"] == "length":
            p1, p2 = measurement["points"]
            distance = math.sqrt((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2) * self.pixel_spacing[0]
            measurement["value"] = distance
            measurement["label"] = f"Length: {distance:.1f}mm"
        elif measurement["type"] == "angle":
            p1, p2, p3 = measurement["points"]
            v1 = (p1[0] - p2[0], p1[1] - p2[1])
            v2 = (p3[0] - p2[0], p3[1] - p2[1])
            dot_product = v1[0] * v2[0] + v1[1] * v2[1]
            mag1 = math.sqrt(v1[0]**2 + v1[1]**2)
            mag2 = math.sqrt(v2[0]**2 + v2[1]**2)
            if mag1 == 0 or mag2 == 0:
                angle = 0
            else:
                cos_angle = dot_product / (mag1 * mag2)
                cos_angle = max(-1, min(1, cos_angle))
                angle = math.degrees(math.acos(cos_angle))
            measurement["value"] = angle
            measurement["label"] = f"Angle: {angle:.1f}°"
        
        # Update drag start position
        self.measurement_drag_start = (event.x, event.y)
        
        # Redraw
        self.display_image()
        self.update_measurements_display()
    
    def stop_drag_measurement(self, event):
        """Stop dragging a measurement point"""
        if self.dragging_measurement is not None:
            measurement = self.measurements[self.dragging_measurement]
            self.show_status(f"Measurement adjusted: {measurement['label']}", "info")
        
        self.dragging_measurement = None
        self.dragging_measurement_point = None
        self.measurement_drag_start = None
        self.canvas.config(cursor="cross")
    
    def draw_measurements(self):
        """Draw all measurements on the canvas"""
        # Helper function to convert image coordinates to canvas coordinates (same as existing code)
        def scaled(pt):
            return pt[0] * self.zoom + self.offset[0], pt[1] * self.zoom + self.offset[1]
        
        for measurement in self.measurements:
            points = measurement["points"]
            
            if measurement["type"] == "length" and len(points) == 2:
                # Draw line
                p1, p2 = points
                x1, y1 = scaled(p1)
                x2, y2 = scaled(p2)
                
                self.canvas.create_line(x1, y1, x2, y2, fill="blue", width=2, tags="measurement")
                
                # Draw measurement points
                self.canvas.create_oval(x1-3, y1-3, x1+3, y1+3, fill="blue", tags="measurement")
                self.canvas.create_oval(x2-3, y2-3, x2+3, y2+3, fill="blue", tags="measurement")
                
                # Draw label
                mid_x, mid_y = (x1 + x2) / 2, (y1 + y2) / 2
                self.canvas.create_text(mid_x, mid_y - 15, text=measurement["label"], 
                                       fill="blue", font=("Arial", 9, "bold"), tags="measurement")
                                       
            elif measurement["type"] == "angle" and len(points) == 3:
                # Draw angle lines
                p1, p2, p3 = points
                x1, y1 = scaled(p1)
                x2, y2 = scaled(p2)  # vertex
                x3, y3 = scaled(p3)
                
                self.canvas.create_line(x2, y2, x1, y1, fill="green", width=2, tags="measurement")
                self.canvas.create_line(x2, y2, x3, y3, fill="green", width=2, tags="measurement")
                
                # Draw measurement points
                self.canvas.create_oval(x1-3, y1-3, x1+3, y1+3, fill="green", tags="measurement")
                self.canvas.create_oval(x2-3, y2-3, x2+3, y2+3, fill="green", tags="measurement")
                self.canvas.create_oval(x3-3, y3-3, x3+3, y3+3, fill="green", tags="measurement")
                
                # Draw angle arc (simplified)
                self.canvas.create_text(x2, y2 - 20, text=measurement["label"], 
                                       fill="green", font=("Arial", 9, "bold"), tags="measurement")
    
        # Draw temporary measurement points during creation
        for i, point in enumerate(self.measurement_points):
            x, y = scaled(point)
            color = "blue" if self.current_measurement_tool == "length" else "green"
            self.canvas.create_oval(x-4, y-4, x+4, y+4, fill=color, tags="measurement")  
    
    def start_drag_screw(self, event):
        """Check if we're clicking on a screw to drag it"""
        if self.image is None or self.current_screw == "placing":
            return
        
        # Convert click position to image coordinates
        x = (event.x - self.offset[0]) / self.zoom
        y = (event.y - self.offset[1]) / self.zoom
        
        # Check if we're near any screw head or tip
        threshold = 10 / self.zoom  # 10 pixels threshold, adjusted for zoom
        
        for i, screw in enumerate(self.screws):
            head_x, head_y = screw["head"]
            tip_x, tip_y = screw["tip"]
            
            # Check if near head
            if math.sqrt((x - head_x)**2 + (y - head_y)**2) < threshold:
                self.dragging_screw = i
                self.dragging_screw_part = "head"
                self.screw_drag_start = (event.x, event.y)
                self.canvas.config(cursor="fleur")
                return
            
            # Check if near tip
            if math.sqrt((x - tip_x)**2 + (y - tip_y)**2) < threshold:
                self.dragging_screw = i
                self.dragging_screw_part = "tip"
                self.screw_drag_start = (event.x, event.y)
                self.canvas.config(cursor="fleur")
                return
    
    def on_drag_screw(self, event):
        """Drag a screw head or tip to new position"""
        if self.dragging_screw is None or self.screw_drag_start is None:
            return
        
        # Calculate movement in image coordinates
        dx = (event.x - self.screw_drag_start[0]) / self.zoom
        dy = (event.y - self.screw_drag_start[1]) / self.zoom
        
        # Update screw position
        screw = self.screws[self.dragging_screw]
        
        if self.dragging_screw_part == "head":
            old_x, old_y = screw["head"]
            screw["head"] = (old_x + dx, old_y + dy)
        else:  # tip
            old_x, old_y = screw["tip"]
            screw["tip"] = (old_x + dx, old_y + dy)
        
        # Recalculate length only (keep original diameter)
        head_x, head_y = screw["head"]
        tip_x, tip_y = screw["tip"]
        length = math.sqrt((tip_x - head_x)**2 + (tip_y - head_y)**2) * self.pixel_spacing[0]
        screw["length"] = round(length)
        # Note: Diameter remains unchanged during dragging
        
        # Update drag start position
        self.screw_drag_start = (event.x, event.y)
        
        # Redraw
        self.display_image()
        self.update_implant_summary()
    
    def stop_drag_screw(self, event):
        """Stop dragging a screw"""
        if self.dragging_screw is not None:
            screw = self.screws[self.dragging_screw]
            self.show_status(
                f"Screw adjusted: {screw['level']} - Ø{screw['diameter']}mm x {screw['length']}mm", 
                "info"
            )
        
        self.dragging_screw = None
        self.dragging_screw_part = None
        self.screw_drag_start = None
        self.canvas.config(cursor="cross")
                
        
    def start_drag_cage(self, event):
        """Check if we're clicking on a cage to drag it"""
        if self.image is None:
            return
        
        # Get the item under the cursor
        item = self.canvas.find_closest(event.x, event.y)
        if item:
            tags = self.canvas.gettags(item[0])
            # Skip if we clicked on a label
            if "cage_label" in tags:
                return
        
        # Convert click position to image coordinates
        x = (event.x - self.offset[0]) / self.zoom
        y = (event.y - self.offset[1]) / self.zoom
        
        # Check if click is inside any interbody cage
        for i, cage in enumerate(self.cages):
            corners = cage["corners"]
            # Check if point is inside the quadrilateral
            if self.point_in_quad(x, y, corners):
                self.dragging_cage = i
                self.cage_drag_start = (event.x, event.y)
                self.canvas.config(cursor="fleur")
                return
        
        # Check corpectomy cages
        for i, cage in enumerate(self.corpectomy_cages):
            if "center" in cage:  # Template style
                center = cage["center"]
                radius = cage.get("radius", 20)
                if math.sqrt((x - center[0])**2 + (y - center[1])**2) < radius:
                    self.dragging_cage = ("corpectomy", i)
                    self.cage_drag_start = (event.x, event.y)
                    self.canvas.config(cursor="fleur")
                    return
            elif "top" in cage and "bottom" in cage:  # Draw style
                # Check if click is near the line between top and bottom
                top = cage["top"]
                bottom = cage["bottom"]
                # Calculate distance from point to line segment
                line_dist = self.point_to_line_distance(x, y, top, bottom)
                if line_dist < (cage.get("diameter", 20) / self.pixel_spacing[0] / 2):
                    self.dragging_cage = ("corpectomy", i)
                    self.cage_drag_start = (event.x, event.y)
                    self.canvas.config(cursor="fleur")
                    return
    
    def point_to_line_distance(self, px, py, line_start, line_end):
        """Calculate distance from point to line segment"""
        x1, y1 = line_start
        x2, y2 = line_end
        
        # Calculate the distance from point to line segment
        A = px - x1
        B = py - y1
        C = x2 - x1
        D = y2 - y1
        
        dot = A * C + B * D
        len_sq = C * C + D * D
        
        if len_sq == 0:
            return math.sqrt(A * A + B * B)
        
        param = dot / len_sq
        
        if param < 0:
            xx, yy = x1, y1
        elif param > 1:
            xx, yy = x2, y2
        else:
            xx = x1 + param * C
            yy = y1 + param * D
        
        dx = px - xx
        dy = py - yy
        return math.sqrt(dx * dx + dy * dy)
    
    def point_in_quad(self, x, y, corners):
        """Check if a point is inside a quadrilateral using ray casting"""
        if len(corners) != 4:
            return False
        
        # Ray casting algorithm
        inside = False
        p1x, p1y = corners[-1]
        for p2x, p2y in corners:
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y
        return inside
    
    def create_cage_handles(self, cage_index):
        """Create resize handles for a selected cage"""
        cage = self.cages[cage_index]
        corners = cage["corners"]
        
        self.cage_handles = []
        for i, (x, y) in enumerate(corners):
            sx, sy = x * self.zoom + self.offset[0], y * self.zoom + self.offset[1]
            handle = self.canvas.create_rectangle(sx-4, sy-4, sx+4, sy+4, 
                                                 fill='white', outline='red', width=2, 
                                                 tags=("cage_handle", f"handle_{i}"))
            self.cage_handles.append(handle)
        
        self.selected_cage = cage_index
        self.resizing_cage = False
    
    def start_resize_cage(self, event):
        """Start resizing a cage by dragging its corner handle"""
        item = self.canvas.find_closest(event.x, event.y)
        if item:
            tags = self.canvas.gettags(item[0])
            if "cage_handle" in tags:
                # Find which handle was clicked
                for tag in tags:
                    if tag.startswith("handle_"):
                        self.resizing_handle = int(tag.split("_")[1])
                        self.resizing_cage = True
                        self.resize_start = (event.x, event.y)
                        self.canvas.config(cursor="sizing")
                        return
    
    def on_resize_cage(self, event):
        """Resize cage by dragging handle"""
        if not self.resizing_cage or self.selected_cage is None:
            return
        
        # Update the corner position directly from mouse coordinates
        x = (event.x - self.offset[0]) / self.zoom
        y = (event.y - self.offset[1]) / self.zoom
        
        # Update the corner position immediately
        self.cages[self.selected_cage]["corners"][self.resizing_handle] = (x, y)
        
        # Only recalculate dimensions, don't recreate handles during drag
        cage = self.cages[self.selected_cage]
        points = cage["corners"]
        
        # Recalculate dimensions
        bottom_width = math.sqrt((points[1][0] - points[0][0])**2 + 
                                (points[1][1] - points[0][1])**2) * self.pixel_spacing[0]
        top_width = math.sqrt((points[3][0] - points[2][0])**2 + 
                             (points[3][1] - points[2][1])**2) * self.pixel_spacing[0]
        width = (bottom_width + top_width) / 2
        
        left_height = math.sqrt((points[2][0] - points[0][0])**2 + 
                               (points[2][1] - points[0][1])**2) * self.pixel_spacing[1]
        right_height = math.sqrt((points[3][0] - points[1][0])**2 + 
                                (points[3][1] - points[1][1])**2) * self.pixel_spacing[1]
        height = (left_height + right_height) / 2
        
        lordosis = math.degrees(math.atan2(abs(top_width - bottom_width), height))
        
        # Update cage dimensions
        cage["width"] = round(width, 1)
        cage["height"] = round(height, 1)
        cage["lordosis"] = round(lordosis, 1)
        
        # Redraw only the image and cages, not the handles during dragging
        self.display_image()
        # Update handle positions without recreating them
        self.update_cage_handles()
        self.update_implant_summary()
    
    def update_cage_handles(self):
        """Update positions of existing cage handles without recreating them"""
        if self.selected_cage is None or not self.cage_handles:
            return
        
        cage = self.cages[self.selected_cage]
        corners = cage["corners"]
        
        for i, (x, y) in enumerate(corners):
            if i < len(self.cage_handles):
                sx, sy = x * self.zoom + self.offset[0], y * self.zoom + self.offset[1]
                # Move existing handle instead of recreating it
                self.canvas.coords(self.cage_handles[i], sx-4, sy-4, sx+4, sy+4)
    
    def stop_resize_cage(self, event):
        """Stop resizing cage"""
        if self.resizing_cage and self.selected_cage is not None:
            cage = self.cages[self.selected_cage]
            self.show_status(f"Cage resized: {cage['width']}×{cage['height']}mm, {cage['lordosis']}° lordosis", "info")
            
            # Now recreate handles with final positions
            self.create_cage_handles(self.selected_cage)
        
        self.resizing_cage = False
        self.resizing_handle = None
        self.canvas.config(cursor="cross")
        
        # Remove handles after a delay
        self.root.after(2000, self.clear_cage_handles)
    
    def clear_cage_handles(self):
        """Remove cage resize handles"""
        self.canvas.delete("cage_handle")
        self.selected_cage = None
    
    def on_drag_cage(self, event):
        """Drag a cage to new position"""
        if self.dragging_cage is None or self.cage_drag_start is None:
            return
        
        # Calculate movement in image coordinates
        dx = (event.x - self.cage_drag_start[0]) / self.zoom
        dy = (event.y - self.cage_drag_start[1]) / self.zoom
        
        # Move the appropriate cage
        if isinstance(self.dragging_cage, tuple) and self.dragging_cage[0] == "corpectomy":
            # Dragging a corpectomy cage
            _, idx = self.dragging_cage
            cage = self.corpectomy_cages[idx]
            if "center" in cage:
                old_x, old_y = cage["center"]
                cage["center"] = (old_x + dx, old_y + dy)
            elif "top" in cage and "bottom" in cage:
                cage["top"] = (cage["top"][0] + dx, cage["top"][1] + dy)
                cage["bottom"] = (cage["bottom"][0] + dx, cage["bottom"][1] + dy)
        else:
            # Dragging an interbody cage
            cage = self.cages[self.dragging_cage]
            # Move all corners
            for i in range(len(cage["corners"])):
                old_x, old_y = cage["corners"][i]
                cage["corners"][i] = (old_x + dx, old_y + dy)
        
        # Update drag start position
        self.cage_drag_start = (event.x, event.y)
        
        # Redraw
        self.display_image()
    
    def stop_drag_cage(self, event):
        """Stop dragging a cage"""
        if self.dragging_cage is not None:
            if isinstance(self.dragging_cage, tuple):
                cage_type = "Corpectomy cage"
            else:
                cage = self.cages[self.dragging_cage]
                cage_type = f"{cage['level']} cage"
            self.show_status(f"{cage_type} repositioned", "info")
        
        self.dragging_cage = None
        self.cage_drag_start = None
        self.canvas.config(cursor="cross")
    
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
    
    def draw_calibration_line(self):
        """Draw the calibration line if it exists"""
        if self.is_calibrated and hasattr(self, 'calibration_points') and len(self.calibration_points) == 2:
            p1, p2 = self.calibration_points
            x1 = p1[0] * self.zoom + self.offset[0]
            y1 = p1[1] * self.zoom + self.offset[1]
            x2 = p2[0] * self.zoom + self.offset[0]
            y2 = p2[1] * self.zoom + self.offset[1]
            
            # Draw the calibration line
            self.canvas.create_line(x1, y1, x2, y2, fill='lime', width=2, 
                                  tags="calibration", dash=(5, 3))
            
            # Draw endpoints
            self.canvas.create_oval(x1-3, y1-3, x1+3, y1+3, fill='lime', 
                                  outline='darkgreen', tags="calibration")
            self.canvas.create_oval(x2-3, y2-3, x2+3, y2+3, fill='lime', 
                                  outline='darkgreen', tags="calibration")
            
            # Calculate and display the calibrated distance
            pixel_dist = math.sqrt((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2)
            real_dist = pixel_dist * self.pixel_spacing[0]
            
            # Place text at the midpoint of the line
            mid_x = (x1 + x2) / 2
            mid_y = (y1 + y2) / 2
            
            # Create outlined text for visibility
            text = f"{real_dist:.1f} mm"
            self.create_outlined_text(mid_x + 5, mid_y - 15, text, 
                                    'lime', 10, "calibration")
    
    def start_calibration(self):
        if self.image is None:
            messagebox.showwarning("Warning", "Please load an image first.")
            return
        
        self.calibration_mode = True
        self.calibration_points = []  # This clears previous calibration points
        self.current_landmark_name = None  # Disable landmark placement
        self.info_label.config(text="Calibration: Click first point")
        
        # Don't need to delete the calibration_line_id anymore since display_image handles it
    
    def finish_calibration(self):
        if len(self.calibration_points) != 2:
            return
        
        # Ask user for real-world distance
        dialog = tk.Toplevel(self.root)
        dialog.title("Calibration Distance")
        dialog.geometry("350x200")
        dialog.resizable(False, False)
        dialog.grab_set()  # Make it modal
        
        # Center the dialog
        dialog.transient(self.root)
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        # Calculate the angle of the calibration line
        p1, p2 = self.calibration_points
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        angle = math.degrees(math.atan2(-dy, dx))  # Negative dy for screen coordinates
        
        # Normalize angle to 0-180 range (we don't care about direction)
        angle = abs(angle)
        if angle > 90:
            angle = 180 - angle
        
        # Determine if it's roughly horizontal or vertical
        angle_description = ""
        if angle < 5:
            angle_description = " (horizontal)"
        elif angle > 85:
            angle_description = " (vertical)"
        elif 43 < angle < 47:
            angle_description = " (45° diagonal)"
        
        tk.Label(dialog, text=f"Enter the real distance between\nthe two points (in mm):\n\nLine angle: {angle:.1f}°{angle_description}", 
             font=("Arial", 10)).pack(pady=10)
        
        distance_var = tk.StringVar()
        entry = tk.Entry(dialog, textvariable=distance_var, font=("Arial", 12), width=15)
        entry.pack(pady=5)
        entry.focus()
        
        self.update_calibration_status()
        
        def apply_calibration():
            try:
                real_distance = float(distance_var.get())
                if real_distance <= 0:
                    raise ValueError("Distance must be positive")
                
                # Calculate pixel distance
                p1, p2 = self.calibration_points
                pixel_distance = math.sqrt((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2)
                
                # Calculate pixel spacing (mm per pixel)
                mm_per_pixel = real_distance / pixel_distance
                self.pixel_spacing = [mm_per_pixel, mm_per_pixel]
                self.is_calibrated = True
                
                self.calibration_angle = angle
                
                self.calibration_mode = False
                # Don't clear calibration_points anymore - we need them to draw the line
                
                angle_info = f" (calibration line: {angle:.1f}°{angle_description})"
                self.info_label.config(text=f"Calibrated: {mm_per_pixel:.3f} mm/pixel{angle_info}")
                
                self.update_calibration_status()
                
                # Update all existing measurements
                self.update_measurements()
                self.display_image()  # This will now draw the calibration line
                
                dialog.destroy()
                
            except ValueError as e:
                messagebox.showerror("Error", "Please enter a valid positive number.")
        
        def cancel_calibration():
            self.calibration_mode = False
            self.calibration_points = []
            if self.calibration_line_id:
                self.canvas.delete(self.calibration_line_id)
                self.calibration_line_id = None
            self.info_label.config(text="Calibration cancelled.")
            dialog.destroy()
        
        button_frame = tk.Frame(dialog)
        button_frame.pack(pady=15)
        
        tk.Button(button_frame, text="Apply", command=apply_calibration, 
                  bg="lightgreen", width=10).pack(side="left", padx=5)
        tk.Button(button_frame, text="Cancel", command=cancel_calibration, 
                  bg="lightcoral", width=10).pack(side="left", padx=5)
        
        # Bind Enter key to apply
        entry.bind('<Return>', lambda e: apply_calibration())
    
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
        if self.applied_cages:
            tk.Label(scrollable_frame, text="Cages:", bg="white",
                     font=("Arial", 9, "bold")).pack(anchor="w", pady=(10, 0))
            sorted_cages = sorted(
                enumerate(self.applied_cages),
                key=lambda x: vertebral_level_order(x[1].get("level", ""))
            )
            for i, (orig_idx, cage) in enumerate(sorted_cages):
                level     = cage.get("level", "")
                ant_h     = cage.get("ant_height", "—")
                post_h    = cage.get("post_height", "—")
                lordosis  = cage.get("lordosis", "—")
                unit      = cage.get("unit", "")
                row = tk.Frame(scrollable_frame, bg="white")
                row.pack(fill="x", pady=1)
                tk.Label(
                    row,
                    text=f"{i+1}. {level}  |  {ant_h}{unit} ant / {post_h}{unit} post  |  {lordosis}°",
                    bg="white"
                ).pack(side="left")
                tk.Button(
                    row, text="×",
                    command=lambda idx=orig_idx: self.delete_applied_cage(idx),
                    bg="white", fg="red", bd=0, font=("Arial", 9, "bold")
                ).pack(side="right")
                
            # Add osteotomies to summary
        if self.osteotomies:
            tk.Label(scrollable_frame, text="Osteotomies:", bg="white", font=("Arial", 9, "bold")).pack(anchor="w", pady=(10,0))
            
            for i, osteotomy in enumerate(self.osteotomies):
                level = osteotomy.get("level", "")
                angle = osteotomy.get("angle", 0)
                
                osteotomy_frame = tk.Frame(scrollable_frame, bg="white")
                osteotomy_frame.pack(fill="x", pady=1)
                
                tk.Label(osteotomy_frame, text=f"{i+1}. {level} Osteotomy - {angle:.1f}°", 
                       bg="white").pack(side="left")
                
                # Add delete button
                tk.Button(osteotomy_frame, text="×", command=lambda idx=i: self.delete_osteotomy(idx),
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
            elif implant_type == "corpectomy" and 0 <= index < len(self.corpectomy_cages):
                del self.corpectomy_cages[index]
                self.show_status(f"Corpectomy cage {index+1} deleted.", "info")
                
            self.update_implant_summary()
            self.display_image()
        except Exception as e:
            self.show_status(f"Failed to delete implant: {str(e)}", "error")

    def calculate_circle(self, p1, p2):
        center_x = (p1[0] + p2[0]) / 2
        center_y = (p1[1] + p2[1]) / 2
        radius = math.sqrt((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2) / 2
        return (center_x, center_y), radius

    def calculate_acute_slope(self, p1, p2):
        """Calculate the acute angle of a line relative to horizontal (0-90 degrees)"""
        dx = (p2[0] - p1[0]) * self.pixel_spacing[1]
        dy = (p2[1] - p1[1]) * self.pixel_spacing[0]
        angle = abs(math.degrees(math.atan2(-dy, dx)))
        
        # Ensure we get the acute angle (0-90 degrees)
        if angle > 90:
            angle = 180 - angle
        
        return angle
    
    def calculate_acute_angle_between_lines(self, p1_start, p1_end, p2_start, p2_end):
        """Calculate the acute angle between two lines defined by their endpoints"""
        # Calculate direction vectors
        dx1 = (p1_end[0] - p1_start[0]) * self.pixel_spacing[1]
        dy1 = (p1_end[1] - p1_start[1]) * self.pixel_spacing[0]
        dx2 = (p2_end[0] - p2_start[0]) * self.pixel_spacing[1]
        dy2 = (p2_end[1] - p2_start[1]) * self.pixel_spacing[0]
        
        # Calculate vectors
        vec1 = np.array([dx1, dy1])
        vec2 = np.array([dx2, dy2])
        
        # Calculate acute angle between vectors
        cos_angle = np.clip(np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2)), -1.0, 1.0)
        angle = math.degrees(math.acos(abs(cos_angle)))
        
        # Ensure acute angle (0-90 degrees)
        return min(angle, 180 - angle)


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
            # Calculate C2 center for C2-C7 SVA
            c2_center_x = (c2a_x + c2p_x) / 2
            c2_center_y = (c2a_y + c2p_y) / 2
            
            # Draw C2-C7 SVA from C2 center to C7 posterior
            self.canvas.create_line(c2_center_x, c2_center_y, c2_center_x, c7p_y, fill=self.colors["C2-C7"], width=1, dash=(4, 2))
            self.canvas.create_line(c2_center_x, c7p_y, c7p_x, c7p_y, fill=self.colors["C2-C7"], width=1, dash=(4, 2))
            
            # Display C2-C7 lordosis
            lordosis = self.calculate_acute_angle_between_lines(
                lm["C2_ant"], lm["C2_post"], lm["C7_ant"], lm["C7_post"]
            )
            
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
            # Calculate C2-C7 SVA value in image coordinates (with sign)
            c2_center_x_img = (lm["C2_ant"][0] + lm["C2_post"][0]) / 2
            c2_c7_sva = (c2_center_x_img - lm["C7_post"][0]) * px  # Keep sign
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
                text=f"C2-C7 SVA: {c2_c7_sva:+.1f}mm",  # Use + to always show sign
                fill_color=self.colors["C2-C7"],
                font_size=self.text_size,
                tags=("label:C2-C7SVA",)
            )
        
        # Draw T1 slope
        if all(k in lm for k in ["T1_ant", "T1_post"]):
            t1a_x, t1a_y = scaled(lm["T1_ant"])
            t1p_x, t1p_y = scaled(lm["T1_post"])
            self.canvas.create_line(t1a_x, t1a_y, t1p_x, t1a_y, fill=self.colors["T1"], width=1, dash=(4, 2))
            t1_slope = self.calculate_acute_slope(lm["T1_ant"], lm["T1_post"])
            
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
        
        # Draw Lumbar Lordosis (L1-S1)
        if all(k in lm for k in ["L1_ant", "L1_post", "S1_ant", "S1_post"]):
            l1a_x, l1a_y = scaled(lm["L1_ant"])
            l1p_x, l1p_y = scaled(lm["L1_post"])
            s1a_x, s1a_y = scaled(lm["S1_ant"])
            s1p_x, s1p_y = scaled(lm["S1_post"])
            
            # Draw L1 endplate
            self.canvas.create_line(l1a_x, l1a_y, l1p_x, l1p_y, fill=self.colors["Lumbar"], width=2)
            # Draw S1 endplate (already drawn in sacral slope, but we can reference it)
            # Connect endplates visually
            self.canvas.create_line(l1a_x, l1a_y, s1a_x, s1a_y, fill=self.colors["Lumbar"], width=1, dash=(5, 3))
            self.canvas.create_line(l1p_x, l1p_y, s1p_x, s1p_y, fill=self.colors["Lumbar"], width=1, dash=(5, 3))
            
            l1_angle = self.calculate_angle(lm["L1_ant"], lm["L1_post"])
            s1_angle = self.calculate_angle(lm["S1_ant"], lm["S1_post"])
            ll = abs(l1_angle - s1_angle)
            # Ensure we get the acute angle
            if ll > 180:
                ll = 360 - ll
            
            # Store L1-S1 midpoint as anchor
            ll_anchor = ((l1a_x + s1a_x)/2 - 25, (l1a_y + s1a_y)/2)
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
            
            s1_slope = self.calculate_acute_slope(lm["S1_ant"], lm["S1_post"])
            
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
            if pt > 90:
                pt = 180 - pt
            
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
            pi_angle = math.degrees(math.acos(abs(cos_pi)))
            pi_angle = min(pi_angle, 180 - pi_angle)
            
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
        sva = None  # Initialize sva variable
        sva_anchor = None  # Initialize anchor variable
        
        if all(k in lm for k in ["C7_ant", "C7_post", "S1_post"]):
            c7a_x, c7a_y = scaled(lm["C7_ant"])
            c7p_x, c7p_y = scaled(lm["C7_post"])
            s1p_x, s1p_y = scaled(lm["S1_post"])
            
            # Calculate C7 center in both coordinate systems
            c7_center_x = (c7a_x + c7p_x) / 2  # Canvas coordinates for drawing
            c7_center_y = (c7a_y + c7p_y) / 2
            c7_center_x_img = (lm["C7_ant"][0] + lm["C7_post"][0]) / 2  # Image coordinates for calculation
            
            # Draw C7 plumbline from C7 center
            self.canvas.create_line(c7_center_x, c7_center_y, c7_center_x, s1p_y, fill=self.colors["SVA"], width=2, dash=(5, 3))
            
            # Draw horizontal line to S1
            self.canvas.create_line(c7_center_x, s1p_y, s1p_x, s1p_y, fill=self.colors["SVA"], width=2)
            
            # Calculate SVA value with sign
            sva = (c7_center_x_img - lm["S1_post"][0]) * px  # Keep sign
            
            # Store SVA anchor point
            sva_anchor = ((c7_center_x + s1p_x) / 2, s1p_y + 20)
            store_anchor_point("SVA", sva_anchor)
            
        elif all(k in lm for k in ["C7_post", "S1_post"]):
            # Fallback if C7_ant not available
            c7p_x, c7p_y = scaled(lm["C7_post"])
            s1p_x, s1p_y = scaled(lm["S1_post"])
            
            # Draw C7 plumbline from posterior (as fallback)
            self.canvas.create_line(c7p_x, c7p_y, c7p_x, s1p_y, fill=self.colors["SVA"], width=2, dash=(5, 3))
            
            # Draw horizontal line to S1
            self.canvas.create_line(c7p_x, s1p_y, s1p_x, s1p_y, fill=self.colors["SVA"], width=2)
            
            # Calculate SVA value with sign
            sva = (lm["C7_post"][0] - lm["S1_post"][0]) * px  # Keep sign
            
            # Store SVA anchor point
            sva_anchor = ((c7p_x + s1p_x) / 2, s1p_y + 20)
            store_anchor_point("SVA", sva_anchor)
        
        # Draw the label if we have SVA calculated
        if sva is not None and sva_anchor is not None:
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
                text=f"SVA: {sva:+.1f}mm",  # Use + to always show sign
                fill_color=self.colors["SVA"],
                font_size=self.text_size,
                tags=("label:SVA",)
            )

    def place_wedge_osteotomy(self):
        """Begin placing a wedge osteotomy on the image"""
        self.current_osteotomy = "placing_wedge"
        self.current_osteotomy_points = []
        level = self.osteotomy_level_var.get()
        self.show_status(
            f"Click to place wedge osteotomy at {level}:\n"
            f"1) Anterior point of wedge\n"
            f"2) Superior posterior point\n" 
            f"3) Inferior posterior point",
            "info",
            persistent=True
        )
    
    def calculate_wedge_angle(self, points):
        """Calculate the angle of the wedge to be removed"""
        if len(points) != 3:
            return 0
        
        anterior, sup_post, inf_post = points
        
        # Vector from anterior to superior posterior
        vec1 = np.array([sup_post[0] - anterior[0], sup_post[1] - anterior[1]])
        # Vector from anterior to inferior posterior  
        vec2 = np.array([inf_post[0] - anterior[0], inf_post[1] - anterior[1]])
        
        # Normalize vectors
        vec1_norm = vec1 / np.linalg.norm(vec1)
        vec2_norm = vec2 / np.linalg.norm(vec2)
        
        # Calculate angle using atan2 for proper quadrant
        angle1 = math.atan2(vec1_norm[1], vec1_norm[0])
        angle2 = math.atan2(vec2_norm[1], vec2_norm[0])
        
        # Get the difference
        angle_diff = angle1 - angle2
        
        # Normalize to [0, 2π]
        while angle_diff < 0:
            angle_diff += 2 * math.pi
        while angle_diff > 2 * math.pi:
            angle_diff -= 2 * math.pi
            
        # Convert to degrees and take the smaller angle
        angle_degrees = math.degrees(angle_diff)
        if angle_degrees > 180:
            angle_degrees = 360 - angle_degrees
            
        print(f"DEBUG: Calculated wedge angle: {angle_degrees:.1f}°")
        return angle_degrees
    
    def delete_osteotomy(self, index):
        """Remove an osteotomy from the list and reapply remaining ones"""
        try:
            if 0 <= index < len(self.osteotomies):
                removed = self.osteotomies.pop(index)
                self.show_status(f"Osteotomy at {removed['level']} deleted.", "info")
                
                # Reapply all remaining osteotomies
                if self.osteotomies:
                    self.apply_all_osteotomies()
                else:
                    # No osteotomies left, restore original
                    self.reset_all_osteotomies()
                
                self.update_implant_summary()
                self.display_image()
                self.update_measurements()
                
        except Exception as e:
            self.show_status(f"Failed to delete osteotomy: {str(e)}", "error")
    
    def reset_all_osteotomies(self):
        """Reset all osteotomies"""
        # Restore original image and landmarks
        if hasattr(self, 'original_landmarks_backup') and self.original_landmarks_backup:
            self.landmarks = self.original_landmarks_backup.copy()
        
        if self.original_image:
            self.image = self.original_image.copy()
        
        # Clear all osteotomy data
        self.osteotomies = []
        self.current_osteotomy_points = []
        self.current_osteotomy = None
        
        # Reset button states
        self.apply_osteotomy_button.config(state="disabled")
        self.reset_osteotomy_button.config(state="disabled") 
        self.place_osteotomy_button.config(state="normal")
        
        # Reset correction display
        self.correction_label.config(text="Place osteotomy points first")
        
        # Update display and measurements
        self.display_image()
        self.update_measurements()
        self.update_implant_summary()
        
        self.show_status("All osteotomies reset", "info")
    
    def detect_image_orientation(self, anterior_point, sup_post_point, inf_post_point):
        """Detect if patient is facing left or right based on point positions"""
        anterior_x = anterior_point[0]
        posterior_x = (sup_post_point[0] + inf_post_point[0]) / 2
        
        # If anterior is to the left of posterior, patient faces left
        # If anterior is to the right of posterior, patient faces right
        if anterior_x < posterior_x:
            return "sagittal_left"  # Patient facing left
        else:
            return "sagittal_right"  # Patient facing right
    
    def apply_osteotomy(self):
        """Apply the current osteotomy and add it to the list"""
        if len(self.current_osteotomy_points) != 3:
            self.show_status("Place all 3 osteotomy points first.", "error")
            return
        
        # Calculate the correction angle
        angle = self.calculate_wedge_angle(self.current_osteotomy_points)
        level = self.osteotomy_level_var.get()
        
        # Create osteotomy data
        osteotomy_data = {
            "points": self.current_osteotomy_points.copy(),
            "angle": angle,
            "level": level,
            "applied": True
        }
        
        # Add to osteotomies list
        self.osteotomies.append(osteotomy_data)
        
        # Clear current osteotomy state
        self.current_osteotomy_points = []
        self.current_osteotomy = None
        
        # Apply ALL osteotomies fresh
        self.apply_all_osteotomies()
        
        # Reset button states
        self.apply_osteotomy_button.config(state="disabled")
        self.reset_osteotomy_button.config(state="normal")
        
        # Update display and measurements
        self.display_image()
        
        # Update both baseline and estimated measurements
        self.update_measurements(estimated=False)  # Update baseline with original landmarks
        self.update_measurements(estimated=True)   # Update estimated with transformed landmarks
        
        self.update_implant_summary()
        
        self.show_status(f"Osteotomy applied: {angle:.1f}° correction at {level}", "success")
    
    def apply_all_osteotomies(self):
        """Apply all osteotomies in sequence with proper canvas expansion"""
        if not self.original_image:
            return
        
        # Start with original image
        current_image = self.original_image.copy()
        current_landmarks = {}
        
        # Store original landmarks if we haven't already
        if not hasattr(self, 'original_landmarks_backup'):
            self.original_landmarks_backup = {}
            for name in self.landmarks:
                self.original_landmarks_backup[name] = self.landmarks[name]
        
        # Reset landmarks to original positions
        current_landmarks = self.original_landmarks_backup.copy()
        
        # Apply each osteotomy in sequence
        for osteotomy in self.osteotomies:
            if osteotomy["applied"]:
                current_image, current_landmarks = self.apply_single_osteotomy_with_expansion(
                    current_image, current_landmarks, osteotomy["points"], osteotomy["angle"]
                )
        
        # Update the current image and landmarks
        self.image = current_image
        self.landmarks = current_landmarks
    
    def apply_single_osteotomy_with_expansion(self, img, landmarks, osteotomy_points, angle):
        """Simple osteotomy using PIL's built-in crop and rotate functions"""
        if len(osteotomy_points) != 3:
            return img, landmarks
        
        from PIL import ImageDraw
        import numpy as np
        
        anterior, sup_post, inf_post = osteotomy_points
        orientation = self.detect_image_orientation(*osteotomy_points)
        
        # Adjust rotation direction based on orientation
        if orientation == "sagittal_left":
            rotation_direction = -1  # Clockwise for left-facing
        else:  # sagittal_right
            rotation_direction = 1   # Counter-clockwise for right-facing
             
        # Create a mask to identify regions
        mask = Image.new('L', img.size, 0)
        draw = ImageDraw.Draw(mask)
        
        # Define the regions:
        # 1. Superior segment (above superior cut line)
        # 2. Inferior segment (below inferior cut line)
        # The wedge between them will be removed
        
        # Create polygons for each region
        # Superior region - extends from superior cut line upward
        width, height = img.size
        superior_polygon = [
            (0, 0),  # top-left
            (width, 0),  # top-right
            (width, height),  # bottom-right (will be clipped by line)
            (0, height),  # bottom-left (will be clipped by line)
        ]
        
        # Use the superior cut line to clip the polygon
        # We'll create a simple rectangular region above the line
        # This is a simplification but avoids complex polygon clipping
        
        # Instead, let's use a different approach:
        # 1. Crop the image into two parts
        # 2. Rotate the top part
        # 3. Paste them back together
        
        # Find the bounding box of the osteotomy
        y_anterior = int(anterior[1])
        y_sup = int(sup_post[1])
        y_inf = int(inf_post[1])
        
        # Determine the cut line (use average y-coordinate for simplicity)
        cut_y = int((sup_post[1] + inf_post[1]) / 2)
        wedge_height = int(abs(sup_post[1] - inf_post[1]))
        
        # Crop the image into superior and inferior parts
        superior_part = img.crop((0, 0, width, cut_y))
        inferior_part = img.crop((0, cut_y, width, height))
        
        # Rotate the superior part around the anterior point
        # First, calculate the rotation center relative to the superior part
        rotation_center = (int(anterior[0]), int(anterior[1]))
        
        # Use the same rotation angle as the image
        angle_rad = math.radians(angle)  # Same as image rotation
        
        # Calculate the wedge angle
        wedge_angle = self.calculate_wedge_angle(osteotomy_points)
        
        # Rotate using PIL's rotate function
        # Use negative angle because PIL rotates counter-clockwise
        rotated_superior = superior_part.rotate(
            rotation_direction * wedge_angle,  # Apply direction multiplier
            center=rotation_center,
            fillcolor=int(self.get_background_color(np.array(img)))
        )
        
        # Create a new image and paste the parts
        result = Image.new(img.mode, img.size, int(self.get_background_color(np.array(img))))
        
        # Paste the rotated superior part
        result.paste(rotated_superior, (0, 0))
        
        # Paste the inferior part (shifted up by the wedge height)
        wedge_height = int(abs(y_sup - y_inf))
        result.paste(inferior_part, (0, cut_y - wedge_height))
        
        # Transform landmarks
        # Transform landmarks with orientation awareness
        new_landmarks = {}
        orientation = self.detect_image_orientation(anterior, sup_post, inf_post)
        rotation_direction = 1 if orientation == "sagittal_left" else -1
        
        # Apply direction to angle
        corrected_angle_rad = rotation_direction * angle_rad
        
        for name, (lx, ly) in landmarks.items():
            if ly < cut_y:  # Superior segment
                # Apply rotation around anterior point with correct direction
                dx = lx - anterior[0]
                dy = ly - anterior[1]
                new_x = anterior[0] + dx * math.cos(corrected_angle_rad) - dy * math.sin(corrected_angle_rad)
                new_y = anterior[1] + dx * math.sin(corrected_angle_rad) + dy * math.cos(corrected_angle_rad)
                new_landmarks[name] = (new_x, new_y)
            else:  # Inferior segment
                # Just shift up by wedge height
                new_landmarks[name] = (lx, ly - wedge_height)
        
        return result, new_landmarks
    
    def transform_image_with_osteotomy(self):
        """Transform the actual image to show the osteotomy correction"""
        if not self.image or len(self.osteotomy_points) != 3:
            return
        
        anterior, sup_post, inf_post = self.osteotomy_points
        
        # Convert PIL image to numpy array for processing
        img_array = np.array(self.image)
        height, width = img_array.shape[:2]
        
        # Create coordinate grids
        y_coords, x_coords = np.mgrid[0:height, 0:width]
        
        # Calculate which side of each line each pixel is on
        # For superior line (anterior to sup_post)
        sup_line_dx = sup_post[0] - anterior[0]
        sup_line_dy = sup_post[1] - anterior[1]
        
        # For inferior line (anterior to inf_post)
        inf_line_dx = inf_post[0] - anterior[0]
        inf_line_dy = inf_post[1] - anterior[1]
        
        # Cross product to determine which side of line each pixel is on
        sup_cross = (x_coords - anterior[0]) * sup_line_dy - (y_coords - anterior[1]) * sup_line_dx
        inf_cross = (x_coords - anterior[0]) * inf_line_dy - (y_coords - anterior[1]) * inf_line_dx
        
        # Determine which region each pixel belongs to
        # For a wedge osteotomy, we want to rotate the inferior portion toward the superior portion
        # The key is determining which cross product result indicates "below" the inferior line
        
        # If inf_post is below sup_post (normal anatomical position), 
        # then pixels with positive inf_cross are "below" the inferior line
        below_inferior = inf_cross > 0
        
        # Pixels in the wedge (between the lines) - to be removed
        # This depends on the orientation, but generally the wedge is where:
        # sup_cross >= 0 (below/right of superior line) AND inf_cross <= 0 (above/left of inferior line)
        in_wedge = (sup_cross >= 0) & (inf_cross <= 0)
        
        # Create the transformed image
        transformed_img = img_array.copy()
        
        # Calculate rotation angle for closing the wedge (POSITIVE angle to close)
        rotation_angle = math.radians(self.osteotomy_angle)  # REMOVED the negative sign!
        cos_theta = math.cos(rotation_angle)
        sin_theta = math.sin(rotation_angle)
        
        # Rotation matrix for closing the wedge
        rotation_matrix = np.array([[cos_theta, -sin_theta], 
                                   [sin_theta, cos_theta]])
        
        # Find pixels that need to be rotated (below inferior line)
        below_y, below_x = np.where(below_inferior)
        
        if len(below_y) > 0:
            # Convert to coordinate vectors relative to anterior point (hinge point)
            relative_coords = np.column_stack([below_x - anterior[0], below_y - anterior[1]])
            
            # Apply rotation to close the wedge
            rotated_coords = relative_coords @ rotation_matrix.T
            
            # Convert back to absolute coordinates
            new_x = rotated_coords[:, 0] + anterior[0]
            new_y = rotated_coords[:, 1] + anterior[1]
            
            # Round to integer pixel coordinates
            new_x = np.round(new_x).astype(int)
            new_y = np.round(new_y).astype(int)
            
            # Check bounds and copy pixels
            valid_mask = (new_x >= 0) & (new_x < width) & (new_y >= 0) & (new_y < height)
            
            if np.any(valid_mask):
                valid_old_x = below_x[valid_mask]
                valid_old_y = below_y[valid_mask]
                valid_new_x = new_x[valid_mask]
                valid_new_y = new_y[valid_mask]
                
                # Clear the area that will be transformed
                transformed_img[below_y, below_x] = 0
                
                # Place rotated pixels in new positions
                transformed_img[valid_new_y, valid_new_x] = img_array[valid_old_y, valid_old_x]
        
        # Remove the wedge region (fill with background color)
        wedge_y, wedge_x = np.where(in_wedge)
        if len(wedge_y) > 0:
            # Fill wedge area with interpolated background
            transformed_img[wedge_y, wedge_x] = self.get_background_color(img_array)
        
        # Convert back to PIL Image
        self.image = Image.fromarray(transformed_img)
        
    def get_background_color(self, img_array):
        """Get a representative background color for filling removed areas"""
        # Use the median color of edge pixels as background
        height, width = img_array.shape[:2]
        
        # Sample pixels from the edges
        edge_pixels = []
        edge_pixels.extend(img_array[0, :].flatten())  # Top edge
        edge_pixels.extend(img_array[-1, :].flatten())  # Bottom edge
        edge_pixels.extend(img_array[:, 0].flatten())  # Left edge
        edge_pixels.extend(img_array[:, -1].flatten())  # Right edge
        
        return int(np.median(edge_pixels))
    
    def transform_landmarks_with_osteotomy(self, osteotomy_points, osteotomy_angle):
        """Transform landmarks to match the osteotomy correction"""
        if len(osteotomy_points) != 3:
            return
        
        anterior, sup_post, inf_post = osteotomy_points
        
        # Calculate rotation angle (POSITIVE for posterior rotation)
        # Detect orientation and adjust rotation direction
        orientation = self.detect_image_orientation(anterior, sup_post, inf_post)
        rotation_direction = 1 if orientation == "sagittal_left" else -1
        
        # Apply direction to angle
        corrected_rotation_angle = math.radians(rotation_direction * osteotomy_angle)
        
        # Create rotation matrix with correct direction
        cos_theta = math.cos(corrected_rotation_angle)
        sin_theta = math.sin(corrected_rotation_angle)
        rotation_matrix = np.array([[cos_theta, -sin_theta], 
                                   [sin_theta, cos_theta]])
        
        
        # Determine which landmarks should be rotated
        # Calculate which side of the inferior line landmarks are on
        inf_line_dx = inf_post[0] - anterior[0]
        inf_line_dy = inf_post[1] - anterior[1]
        
        for name, (x, y) in self.landmarks.items():
            # Check if landmark is below the inferior osteotomy line
            cross_product = (x - anterior[0]) * inf_line_dy - (y - anterior[1]) * inf_line_dx
            
            # If landmark is on the "inferior" side of the cut (cross_product > 0)
            if cross_product > 0:
                # Translate to origin (anterior point - the hinge)
                point = np.array([x, y]) - np.array(anterior)
                # Apply rotation to close the wedge
                rotated_point = rotation_matrix @ point
                # Translate back
                new_point = rotated_point + np.array(anterior)
                self.landmarks[name] = (new_point[0], new_point[1])
    
    def reset_osteotomy(self):
        """Reset the osteotomy simulation"""
        # Restore original landmarks
        if hasattr(self, 'original_landmarks') and self.original_landmarks:
            self.landmarks = self.original_landmarks.copy()
            self.original_landmarks = {}
        
        # Restore original image
        if hasattr(self, 'original_transformed_image') and self.original_transformed_image:
            self.image = self.original_transformed_image.copy()
            self.original_transformed_image = None
        
        # Clear osteotomy state
        self.osteotomy_points = []
        self.osteotomy_applied = False
        self.osteotomy_angle = 0
        self.current_osteotomy = None
        
        # Reset button states
        self.apply_osteotomy_button.config(state="disabled")
        self.reset_osteotomy_button.config(state="disabled") 
        self.place_osteotomy_button.config(state="normal")
        
        # Reset correction display
        self.correction_label.config(text="Place osteotomy points first")
        
        # Update display and measurements
        self.display_image()
        self.update_measurements()
        
        self.show_status("Osteotomy reset", "info")
    
    def draw_osteotomy(self):
        """Draw all osteotomy lines and current placement"""
        # Helper function to convert image coordinates to canvas coordinates
        def scaled(pt):
            return pt[0] * self.zoom + self.offset[0], pt[1] * self.zoom + self.offset[1]
        
        # Draw existing applied osteotomies
        for i, osteotomy in enumerate(self.osteotomies):
            if osteotomy["applied"]:
                points = osteotomy["points"]
                if len(points) == 3:
                    anterior, sup_post, inf_post = [scaled(pt) for pt in points]
                    
                    # Draw the cut lines in a different color for applied osteotomies
                    self.canvas.create_line(anterior[0], anterior[1], sup_post[0], sup_post[1], 
                                           fill='green', width=2, dash=(3, 3))
                    self.canvas.create_line(anterior[0], anterior[1], inf_post[0], inf_post[1], 
                                           fill='green', width=2, dash=(3, 3))
                    
                    # Label with osteotomy number
                    mid_x = (sup_post[0] + inf_post[0]) / 2
                    mid_y = (sup_post[1] + inf_post[1]) / 2
                    self.canvas.create_text(mid_x, mid_y - 15, text=f"Ost {i+1}", 
                                           fill='green', anchor='center', font=('Arial', 10, 'bold'))
        
        # Draw current osteotomy being placed
        if len(self.current_osteotomy_points) == 0:
            return
        
        # Draw placed points for current osteotomy
        for i, (x, y) in enumerate(self.current_osteotomy_points):
            sx, sy = scaled((x, y))
            color = 'red' if i == 0 else 'orange'
            self.canvas.create_oval(sx-5, sy-5, sx+5, sy+5, fill=color, outline='white', width=2)
            
            # Label the points
            labels = ['Anterior', 'Sup. Post', 'Inf. Post']
            if i < len(labels):
                self.canvas.create_text(sx+8, sy-8, text=labels[i], fill='yellow', anchor='nw', 
                                      font=('Arial', 8, 'bold'))
        
        # Draw current osteotomy lines when we have all 3 points
        if len(self.current_osteotomy_points) == 3:
            anterior, sup_post, inf_post = [scaled(pt) for pt in self.current_osteotomy_points]
            
            # Draw the two cut lines
            self.canvas.create_line(anterior[0], anterior[1], sup_post[0], sup_post[1], 
                                   fill='red', width=3, dash=(5, 5))
            self.canvas.create_line(anterior[0], anterior[1], inf_post[0], inf_post[1], 
                                   fill='red', width=3, dash=(5, 5))
            
            # Draw the wedge area to be removed
            points = [anterior[0], anterior[1], sup_post[0], sup_post[1], inf_post[0], inf_post[1]]
            self.canvas.create_polygon(points, fill='red', stipple='gray25', outline='red', width=2)
            
            # Show the angle
            angle = self.calculate_wedge_angle(self.current_osteotomy_points)
            mid_x = (sup_post[0] + inf_post[0]) / 2
            mid_y = (sup_post[1] + inf_post[1]) / 2
            
            self.canvas.create_text(mid_x, mid_y, text=f"{angle:.1f}°", 
                                   fill='white', anchor='center', font=('Arial', 12, 'bold'))
    def draw_implants(self):
        # Helper function to convert image coordinates to canvas coordinates
        def scaled(pt):
            return pt[0] * self.zoom + self.offset[0], pt[1] * self.zoom + self.offset[1]
            
        # Draw screws
        for i, screw in enumerate(self.screws):
            head_x, head_y = screw["head"]
            tip_x, tip_y = screw["tip"]
            
            # Convert to canvas coordinates
            sx1, sy1 = scaled((head_x, head_y))
            sx2, sy2 = scaled((tip_x, tip_y))
            
            # Draw the screw shaft
            self.canvas.create_line(sx1, sy1, sx2, sy2, fill='yellow', width=3)
            
            # Draw the screw head (larger circle) - make it interactive
            head_oval = self.canvas.create_oval(sx1-6, sy1-6, sx1+6, sy1+6, 
                                              fill='gold', outline='darkgoldenrod', width=2)
            
            # Draw the screw tip (smaller circle) - make it interactive
            tip_oval = self.canvas.create_oval(sx2-4, sy2-4, sx2+4, sy2+4, 
                                             fill='yellow', outline='orange', width=2)
            
            # Add text with screw info
            level = screw.get("level", "")
            diameter = screw.get("diameter", "")
            length = int(screw.get("length", 0))
            self.canvas.create_text(sx1+5, sy1-5, text=f"{level} Ø{diameter}x{length}mm", 
                                   fill='white', anchor="sw", font=('Arial', 9, 'bold'))
        
        # ── Draw committed (applied) cages ──────────────────────────────────────
        import math as _math
        for cage in self.applied_cages:
            if not cage.get("applied"):
                continue
        
            inf_ant  = cage["inf_ant"]
            inf_post = cage["inf_post"]
            sup_ant  = cage["sup_ant"]
            sup_post = cage["sup_post"]
            rot      = cage["rotation_deg"]
            paste_y  = cage["paste_y"]
            px, py   = inf_ant
        
            cos_a = _math.cos(_math.radians(rot))
            sin_a = _math.sin(_math.radians(rot))
        
            def _rot_shift(pt, px=px, py=py, cos_a=cos_a, sin_a=sin_a, paste_y=paste_y):
                dx, dy = pt[0] - px, pt[1] - py
                rx = px + dx * cos_a - dy * sin_a
                ry = py + dx * sin_a + dy * cos_a
                return (rx, ry + paste_y)
        
            # Inferior corners are unchanged; superior corners are rotated + shifted
            corners_transformed = [
                inf_ant,
                inf_post,
                _rot_shift(sup_post),
                _rot_shift(sup_ant),
            ]
        
            poly_pts = []
            for pt in corners_transformed:
                sx, sy = scaled(pt)
                poly_pts.extend([sx, sy])
        
            # Solid cyan outline — visually distinct from preview (orange/gold)
            self.canvas.create_polygon(
                poly_pts,
                outline="#00FFFF", fill="#00FFFF",
                stipple="gray25", width=2,
                tags=("applied_cage",)
            )
        
            # Label at cage centroid
            cx = sum(p[0] for p in corners_transformed) / 4
            cy = sum(p[1] for p in corners_transformed) / 4
            scx, scy = scaled((cx, cy))
            u = cage.get("unit", "mm")
            label = (
                f"{cage.get('level','?')}  "
                f"{cage['ant_height']}{u}A/{cage['post_height']}{u}P  "
                f"{cage['lordosis']}°"
            )
            self.canvas.create_rectangle(
                scx - 60, scy - 9, scx + 60, scy + 9,
                fill="black", stipple="gray50", tags=("applied_cage",)
            )
            self.canvas.create_text(
                scx, scy, text=label,
                fill="#00FFFF", font=("Arial", 8, "bold"),
                anchor="center", tags=("applied_cage",)
            )
    
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

    def update_measurements(self, estimated=False):
        """Update measurements - either baseline or estimated based on current landmarks"""
        target_dict = self.measurement_labels if not estimated else self.estimated_labels
        lm = self.landmarks
        px, py = self.pixel_spacing[1], self.pixel_spacing[0]
        
        def update(name, val, baseline_val=None):
            if not estimated and name in target_dict:
                target_dict[name]["text"] = val
            elif estimated and name in target_dict:
                target_dict[name]["value"]["text"] = val
                # Calculate and show change if we have baseline
                if baseline_val and val != "--" and baseline_val != "--":
                    try:
                        # Extract numeric values
                        est_num = float(val.split()[0])
                        base_num = float(baseline_val.split()[0])
                        change = est_num - base_num
                        change_str = f"({change:+.1f})"
                        color = "green" if abs(change) < 5 else "orange" if abs(change) < 10 else "red"
                        target_dict[name]["change"]["text"] = change_str
                        target_dict[name]["change"]["fg"] = color
                    except:
                        target_dict[name]["change"]["text"] = ""
                else:
                    target_dict[name]["change"]["text"] = ""
    
        # Get baseline values if we're updating estimated
        baseline_values = {}
        if estimated:
            for name, label in self.measurement_labels.items():
                baseline_values[name] = label["text"]
    
        update("CBVA", f"{math.degrees(math.atan2((lm['brow'][0]-lm['chin'][0])*px, -(lm['brow'][1]-lm['chin'][1])*py)):.2f}°") if all(k in lm for k in ["chin", "brow"]) else update("CBVA", "--")
        
        if all(k in lm for k in ["C2_ant", "C2_post", "C7_ant", "C7_post"]):
            c2_c7_lordosis = self.calculate_acute_angle_between_lines(
                lm["C2_ant"], lm["C2_post"], lm["C7_ant"], lm["C7_post"]
            )
            update("C2–C7 Lordosis", f"{c2_c7_lordosis:.2f}°", baseline_values.get("C2–C7 Lordosis") if estimated else None)
        else:
            update("C2–C7 Lordosis", "--")
            
        # C2-C7 SVA: From C2 center to C7 posterior superior corner
        if all(k in lm for k in ["C2_ant", "C2_post", "C7_post"]):
            c2_center_x = (lm['C2_ant'][0] + lm['C2_post'][0]) / 2
            c2_c7_sva = (c2_center_x - lm['C7_post'][0]) * px  # Remove abs() to keep sign
            update("C2–C7 SVA", f"{c2_c7_sva:+.2f} mm", baseline_values.get("C2–C7 SVA") if estimated else None)
        else:
            update("C2–C7 SVA", "--")
            
        if all(k in lm for k in ["T1_ant", "T1_post"]):
            t1_slope = self.calculate_acute_slope(lm['T1_ant'], lm['T1_post'])
            update("T1 Slope", f"{t1_slope:.2f}°", baseline_values.get("T1 Slope") if estimated else None)
        else:
            update("T1 Slope", "--")
        
        if all(k in lm for k in ["L1_ant", "L1_post", "S1_ant", "S1_post"]):
            l1 = self.calculate_angle(lm["L1_ant"], lm["L1_post"])
            s1 = self.calculate_angle(lm["S1_ant"], lm["S1_post"])
            ll = abs(l1 - s1)
            # Ensure we get the acute angle
            if ll > 180:
                ll = 360 - ll
            update("Lumbar Lordosis", f"{ll:.2f}°")
        else:
            update("Lumbar Lordosis", "--")
            
        if all(k in lm for k in ["S1_ant", "S1_post"]):
            sacral_slope = self.calculate_acute_slope(lm['S1_ant'], lm['S1_post'])
            update("Sacral Slope", f"{sacral_slope:.2f}°", baseline_values.get("Sacral Slope") if estimated else None)
        else:
            update("Sacral Slope", "--")
        
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
            # Ensure acute angle for pelvic tilt
            if pt > 90:
                pt = 180 - pt
            update("Pelvic Tilt", f"{pt:.2f}°", baseline_values.get("Pelvic Tilt") if estimated else None)
            
            # Calculate PI using the perpendicular to sacral endplate
            sacral_vec = np.array([(lm["S1_post"][0] - lm["S1_ant"][0]) * px, (lm["S1_post"][1] - lm["S1_ant"][1]) * py])
            sacral_perp = np.array([-sacral_vec[1], sacral_vec[0]])
            sacral_perp = sacral_perp / np.linalg.norm(sacral_perp)
            
            hip_vec = np.array([(bicoxo[0] - sacral_mid[0]) * px, (bicoxo[1] - sacral_mid[1]) * py])
            hip_vec = hip_vec / np.linalg.norm(hip_vec)
            
            cos_pi = np.clip(np.dot(sacral_perp, hip_vec), -1.0, 1.0)
            pi_angle = math.degrees(math.acos(abs(cos_pi)))  # Added abs() here
            pi_angle = min(pi_angle, 180 - pi_angle)  # Ensure acute angle
            
            update("PI (vector)", f"{pi_angle:.2f}°", baseline_values.get("PI (vector)") if estimated else None)
        else:
            update("Pelvic Tilt", "--")
            update("PI (vector)", "--")
            
        # Overall SVA: From C7 center to S1 posterior superior corner
        # Positive = anterior (forward), Negative = posterior (backward)
        if all(k in lm for k in ["C7_ant", "C7_post", "S1_post"]):
            c7_center_x = (lm['C7_ant'][0] + lm['C7_post'][0]) / 2
            overall_sva = (c7_center_x - lm['S1_post'][0]) * px  # Remove abs() to keep sign
            update("SVA", f"{overall_sva:+.2f} mm", baseline_values.get("SVA") if estimated else None)
        elif all(k in lm for k in ["C7_post", "S1_post"]):
            # Fallback if C7_ant not available
            overall_sva = (lm['C7_post'][0] - lm['S1_post'][0]) * px  # Remove abs() to keep sign
            update("SVA", f"{overall_sva:+.2f} mm", baseline_values.get("SVA") if estimated else None)
        else:
            update("SVA", "--")
            
        if self.osteotomies and any(o["applied"] for o in self.osteotomies):
            self.estimated_label.pack(pady=(20,5))
            self.estimated_container.pack(fill="x", padx=5, pady=5)
        else:
            self.estimated_label.pack_forget()
            self.estimated_container.pack_forget()

    def place_screw(self):
        """Begin placing a screw on the image"""
        self.current_screw = "placing"
        self.osteotomy_points = []
        level = self.level_var.get()
        self.show_status(
            f"Click to set the screw entry point at {level}, then click for the trajectory tip.",
            "info",
            persistent=True
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
        