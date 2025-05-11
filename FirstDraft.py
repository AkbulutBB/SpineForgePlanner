import sys
sys.setrecursionlimit(sys.getrecursionlimit() * 5)

import tkinter as tk
from tkinter import filedialog, messagebox
import pydicom
import numpy as np
from PIL import Image, ImageTk, ImageGrab
import math
import pyperclip

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
        measurement_names = [
            "CBVA", "C2–C7 Lordosis", "C2–C7 SVA", "T1 Slope", "Lumbar Lordosis",
            "Sacral Slope", "Pelvic Tilt", "PI (vector)", "PI (sum PT+SS)", "SVA"
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
        self.canvas.bind("<B2-Motion>", self.on_pan)
        self.canvas.bind("<ButtonPress-2>", self.start_pan)

        # Initialize core state
        self.image = None
        self.original_image = None
        self.tk_image = None
        self.zoom = 0.5  # now starts zoomed out
        self.offset = [0, 0]
        self.pan_start = [0, 0]

        self.ds = None
        self.pixel_spacing = [1.0, 1.0]
        self.landmarks = {}
        self.current_landmark_name = None

    def set_current_landmark(self, name):
        self.current_landmark_name = name

    def load_dicom(self):
        filepath = filedialog.askopenfilename(filetypes=[("DICOM files", "*.dcm")])
        if not filepath:
            return
        self.ds = pydicom.dcmread(filepath)
        pixel_array = self.ds.pixel_array.astype(np.float32)
        norm_img = ((pixel_array - np.min(pixel_array)) / np.ptp(pixel_array) * 255).astype(np.uint8)
        self.original_image = Image.fromarray(norm_img)
        self.image = self.original_image
        spacing = self.ds.PixelSpacing
        self.pixel_spacing = [float(spacing[0]), float(spacing[1])]
        self.display_image()

    
    
    def copy_to_clipboard(self):
        text = ""
        for name, label in self.measurement_labels.items():
            text += f"{name}: {label['text']}\n"
        pyperclip.copy(text)
        messagebox.showinfo("Copied", "Measurements copied to clipboard.")

    def display_image(self):
        if self.image is None:
            return
        resized = self.image.resize((int(self.image.width * self.zoom), int(self.image.height * self.zoom)))
        self.tk_image = ImageTk.PhotoImage(resized)
        self.canvas.delete("all")
        self.canvas.create_image(self.offset[0], self.offset[1], anchor="nw", image=self.tk_image)
        self.draw_landmarks()

    def on_click(self, event):
        if not self.current_landmark_name:
            return
        x = int((event.x - self.offset[0]) / self.zoom)
        y = int((event.y - self.offset[1]) / self.zoom)
        self.landmarks[self.current_landmark_name] = (x, y)
        self.current_landmark_name = None
        self.display_image()
        self.update_measurements()

    def draw_landmarks(self):
        for name, (x, y) in self.landmarks.items():
            sx, sy = x * self.zoom + self.offset[0], y * self.zoom + self.offset[1]
            self.canvas.create_oval(sx-3, sy-3, sx+3, sy+3, fill='red')
            self.canvas.create_text(sx+5, sy-5, text=name, fill='yellow', anchor='nw')

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
            s1s = self.calculate_angle(sa, sp)
            update("PI (sum PT+SS)", f"{(pt + abs(s1s)):.2f}°")
        else:
            update("Pelvic Tilt", "--")
            update("PI (vector)", "--")
            update("PI (sum PT+SS)", "--")
        update("SVA", f"{abs((lm['C7_post'][0] - lm['S1_post'][0]) * px):.2f} mm") if all(k in lm for k in ["C7_post", "S1_post"]) else update("SVA", "--")

    def save_screenshot(self):
        x = self.root.winfo_rootx() + self.canvas.winfo_x()
        y = self.root.winfo_rooty() + self.canvas.winfo_y()
        w = x + self.canvas.winfo_width()
        h = y + self.canvas.winfo_height()
        img = ImageGrab.grab().crop((x, y, w, h))
        save_path = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG files", "*.png")])
        if save_path:
            img.save(save_path)
            messagebox.showinfo("Saved", f"Screenshot saved to {save_path}")

    def on_zoom(self, event):
        factor = 1.1 if event.delta > 0 else 0.9
        self.zoom *= factor
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
    app = SpineForgePlanner(root)
    root.mainloop()
