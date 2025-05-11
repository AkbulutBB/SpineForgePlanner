import sys
sys.setrecursionlimit(sys.getrecursionlimit() * 5)

import tkinter as tk
from tkinter import filedialog, messagebox
import pydicom
import numpy as np
from PIL import Image, ImageTk, ImageEnhance
import math
import pyperclip

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

        # Sidebar UI layout
        self.sidebar = tk.Frame(root, width=400, bg="lightgray")
        self.sidebar.pack(side="left", fill="y")

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

        # Landmark buttons in two columns
        button_frame = tk.Frame(self.sidebar, bg="lightgray")
        button_frame.pack(pady=5)
        self.point_buttons = [
            ("Brow", "brow"), ("Chin", "chin"),
            ("C2 Ant", "C2_ant"), ("C2 Post", "C2_post"),
            ("C7 Ant", "C7_ant"), ("C7 Post", "C7_post"),
            ("T1 Ant", "T1_ant"), ("T1 Post", "T1_post"),
            ("L1 Ant", "L1_ant"), ("L1 Post", "L1_post"),
            ("L5 Ant", "L5_ant"), ("L5 Post", "L5_post"),
            ("S1 Ant", "S1_ant"), ("S1 Post", "S1_post"),
            ("Femoral Head", "hip")
        ]
        for i in range(0, len(self.point_buttons), 2):
            row = tk.Frame(button_frame, bg="lightgray")
            row.pack()
            for j in range(2):
                if i + j < len(self.point_buttons):
                    label, name = self.point_buttons[i + j]
                    tk.Button(row, text=label, width=18, command=lambda n=name: self.set_current_landmark(n)).pack(side="left", padx=2, pady=1)

        # Display area for measurements
        self.info_label = tk.Label(self.sidebar, text="Measurements:", bg="lightgray")
        self.info_label.pack(pady=5)
        self.measurement_labels = {}
        self.measurements_frame = tk.Frame(self.sidebar, bg="white")
        self.measurements_frame.pack(fill="x", padx=5, pady=5)
        # Removed 'PI (sum PT+SS)' from the list
        measurement_names = [
            "CBVA", "C2–C7 Lordosis", "C2–C7 SVA", "T1 Slope", "Lumbar Lordosis",
            "Sacral Slope", "Pelvic Tilt", "PI (vector)", "SVA"
        ]
        for name in measurement_names:
            row = tk.Frame(self.measurements_frame, bg="white")
            row.pack(fill="x", pady=1)
            label = tk.Label(row, text=f"{name}:", anchor="w", width=20, bg="white")
            label.pack(side="left")
            val_label = tk.Label(row, text="--", anchor="w", bg="white")
            val_label.pack(side="left")
            self.measurement_labels[name] = val_label

        # Canvas to show image
        self.canvas = tk.Canvas(root, bg="black", cursor="cross")
        self.canvas.pack(fill="both", expand=True)

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

        # Initialize core state
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
                if label['text'] != "--":  # Only include non-empty measurements
                    text += f"{name}: {label['text']}\n"
            pyperclip.copy(text)
            messagebox.showinfo("Copied", "Measurements copied to clipboard.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to copy to clipboard: {str(e)}")

    def display_image(self):
        if self.image is None:
            return
        
        try:
            resized = self.image.resize((int(self.image.width * self.zoom), int(self.image.height * self.zoom)))
            self.tk_image = ImageTk.PhotoImage(resized)
            self.canvas.delete("all")
            self.canvas.create_image(self.offset[0], self.offset[1], anchor="nw", image=self.tk_image)
            self.draw_landmarks()
            self.draw_connecting_lines()  # Add connecting lines after drawing labels
        except Exception as e:
            messagebox.showerror("Error", f"Display error: {str(e)}")

    def on_click(self, event):
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
        if all(k in lm for k in ["S1_ant", "S1_post", "hip"]):
            s1a_x, s1a_y = scaled(lm["S1_ant"])
            s1p_x, s1p_y = scaled(lm["S1_post"])
            hip_x, hip_y = scaled(lm["hip"])
            
            # Calculate midpoint of sacral endplate
            s1_mid_x = (s1a_x + s1p_x) / 2
            s1_mid_y = (s1a_y + s1p_y) / 2
            
            # Draw line from hip to sacral midpoint
            self.canvas.create_line(hip_x, hip_y, s1_mid_x, s1_mid_y, fill=self.colors["Pelvic"], width=2)
            
            # Draw vertical reference line for pelvic tilt
            self.canvas.create_line(hip_x, hip_y, hip_x, s1_mid_y, fill=self.colors["Pelvic"], width=1, dash=(4, 2))
            
            # Calculate pelvic parameters for display
            sa, sp, hip = lm['S1_ant'], lm['S1_post'], lm['hip']
            mid = ((sa[0] + sp[0]) / 2, (sa[1] + sp[1]) / 2)
            dx, dy = (mid[0] - hip[0]) * px, (mid[1] - hip[1]) * py
            pt = abs(math.degrees(math.atan2(dx, -dy)))
            
            vec1 = np.array([dx, dy])
            vec_s1 = np.array([(sp[0] - sa[0]) * px, (sp[1] - sa[1]) * py])
            vec2 = np.array([-vec_s1[1], vec_s1[0]])
            cos_a = np.clip(np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2)), -1.0, 1.0)
            pi_v = math.degrees(math.acos(cos_a))
            pi_v = min(pi_v, 180 - pi_v)
            
            # Calculate midpoint for PT label
            pt_x, pt_y = (hip_x + s1_mid_x) / 2, (hip_y + s1_mid_y) / 2
            
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
                text=f"Pelvic Incidence: {pi_v:.1f}°",
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

    def calculate_angle(self, p1, p2):
        dx = (p2[0] - p1[0]) * self.pixel_spacing[1]
        dy = (p2[1] - p1[1]) * self.pixel_spacing[0]
        return math.degrees(math.atan2(-dy, dx))

    def update_measurements(self):
        lm = self.landmarks
        px, py = self.pixel_spacing[1], self.pixel_spacing[0]
        def update(name, val):
            if name in self.measurement_labels:
                self.measurement_labels[name]["text"] = val

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
        
        if all(k in lm for k in ["S1_ant", "S1_post", "hip"]):
            sa, sp, hip = lm['S1_ant'], lm['S1_post'], lm['hip']
            mid = ((sa[0] + sp[0]) / 2, (sa[1] + sp[1]) / 2)
            dx, dy = (mid[0] - hip[0]) * px, (mid[1] - hip[1]) * py
            pt = abs(math.degrees(math.atan2(dx, -dy)))
            update("Pelvic Tilt", f"{pt:.2f}°")
            
            vec1 = np.array([dx, dy])
            vec_s1 = np.array([(sp[0] - sa[0]) * px, (sp[1] - sa[1]) * py])
            vec2 = np.array([-vec_s1[1], vec_s1[0]])
            cos_a = np.clip(np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2)), -1.0, 1.0)
            pi_v = math.degrees(math.acos(cos_a))
            pi_v = min(pi_v, 180 - pi_v)
            update("PI (vector)", f"{pi_v:.2f}°")
            
            # PI (sum PT+SS) calculation removed as requested
        else:
            update("Pelvic Tilt", "--")
            update("PI (vector)", "--")
            
        update("SVA", f"{abs((lm['C7_post'][0] - lm['S1_post'][0]) * px):.2f} mm") if all(k in lm for k in ["C7_post", "S1_post"]) else update("SVA", "--")

    def save_screenshot(self):
        """Create a screenshot by directly rendering the canvas contents to an image"""
        try:
            if self.image is None:
                messagebox.showinfo("Info", "No image loaded to save.")
                return
                
            # Create a new blank image with the same size as our canvas content
            if hasattr(self, 'image') and self.image:
                # Get the size of the visible content
                canvas_width = self.canvas.winfo_width()
                canvas_height = self.canvas.winfo_height()
                
                # Create a new blank image to draw on
                screenshot = Image.new('RGB', (canvas_width, canvas_height), color='black')
                
                # First draw the medical image
                # Calculate how much of the image is visible within the canvas
                visible_width = min(int(self.image.width * self.zoom), canvas_width)
                visible_height = min(int(self.image.height * self.zoom), canvas_height)
                
                # Calculate source region (of the original image)
                src_x = max(0, int(-self.offset[0] / self.zoom))
                src_y = max(0, int(-self.offset[1] / self.zoom))
                src_width = min(self.image.width - src_x, int(visible_width / self.zoom))
                src_height = min(self.image.height - src_y, int(visible_height / self.zoom))
                
                # Calculate destination region (on the screenshot)
                dst_x = max(0, self.offset[0])
                dst_y = max(0, self.offset[1])
                
                # If there's a visible portion of the image, copy it to the screenshot
                if src_width > 0 and src_height > 0:
                    src_region = self.image.crop((src_x, src_y, src_x + src_width, src_y + src_height))
                    screenshot.paste(src_region, (dst_x, dst_y))
                
                # Create a draw object to add the measurements and annotations
                from PIL import ImageDraw, ImageFont
                draw = ImageDraw.Draw(screenshot)
                
                # Add all the current canvas items to the image
                for item in self.canvas.find_all():
                    type = self.canvas.type(item)
                    
                    # Draw lines and shapes
                    if type == "line":
                        coords = self.canvas.coords(item)
                        width = self.canvas.itemcget(item, 'width')
                        fill = self.canvas.itemcget(item, 'fill')
                        draw.line(coords, fill=fill, width=int(float(width)))
                    
                    elif type == "oval":
                        coords = self.canvas.coords(item)
                        outline = self.canvas.itemcget(item, 'outline')
                        fill = self.canvas.itemcget(item, 'fill')
                        draw.ellipse(coords, outline=outline, fill=fill)
                    
                    elif type == "rectangle":
                        coords = self.canvas.coords(item)
                        outline = self.canvas.itemcget(item, 'outline')
                        fill = self.canvas.itemcget(item, 'fill') 
                        draw.rectangle(coords, outline=outline, fill=fill)
                    
                    # For text, try to add it to the image
                    elif type == "text":
                        coords = self.canvas.coords(item)
                        text = self.canvas.itemcget(item, 'text')
                        fill = self.canvas.itemcget(item, 'fill')
                        
                        # Try to determine font size (default to 12)
                        font_size = 12
                        font_str = self.canvas.itemcget(item, 'font')
                        if font_str:
                            try:
                                # Font string format varies, but often has size as second element
                                font_parts = font_str.split()
                                for part in font_parts:
                                    if part.isdigit():
                                        font_size = int(part)
                                        break
                            except:
                                pass
                        
                        # Create a font object
                        try:
                            font = ImageFont.truetype("arial.ttf", font_size)
                        except:
                            font = ImageFont.load_default()
                        
                        # Draw the text
                        draw.text((coords[0], coords[1]), text, fill=fill, font=font)
                
                # Save the image
                save_path = filedialog.asksaveasfilename(defaultextension=".png", 
                                                       filetypes=[("PNG files", "*.png")])
                if save_path:
                    screenshot.save(save_path)
                    messagebox.showinfo("Saved", f"Screenshot saved to {save_path}")
            else:
                messagebox.showinfo("Info", "No image loaded to save.")
    
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save screenshot: {str(e)}")
            import traceback
            traceback.print_exc()

    def on_zoom(self, event, delta=None):
        if delta is None:  # Windows
            delta = event.delta
            
        old_zoom = self.zoom
        factor = 1.1 if delta > 0 else 0.9
        self.zoom *= factor
        
        # Get cursor position relative to canvas
        cx, cy = event.x, event.y
        
        # Adjust offset so the zoom centers on the cursor position
        self.offset[0] = cx - (cx - self.offset[0]) * (self.zoom / old_zoom)
        self.offset[1] = cy - (cy - self.offset[1]) * (self.zoom / old_zoom)
        
        self.display_image()

    def start_pan(self, event):
        self.pan_start = [event.x, event.y]

    def on_pan(self, event):
        dx = event.x - self.pan_start[0]
        dy = event.y - self.pan_start[1]
        self.offset[0] += dx
        self.offset[1] += dy
        self.pan_start = [event.x, event.y]
        self.display_image()

if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("1200x800")  # Set initial window size
    app = SpineForgePlanner(root)
    root.mainloop()