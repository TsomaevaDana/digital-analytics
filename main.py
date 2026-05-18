import sys
import math
import random
import json
import numpy as np
from enum import Enum
from collections import defaultdict
from PyQt5.QtCore import QByteArray

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QGridLayout, QLabel, QPushButton, QFrame,
                             QScrollArea, QSlider, QSpinBox, QGroupBox,
                             QMessageBox, QFileDialog)
from PyQt5.QtCore import Qt, QPoint, QRect, QPointF, QRectF
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QPolygonF, QPainterPath, QImage

# ------------------------------ Биомы и плиты ------------------------------
class BiomeType(Enum):
    TROPICAL_RAINFOREST = "Тропический лес"
    FOREST = "Лес"
    TAIGA = "Тайга"
    TUNDRA = "Тундра"
    DESERT = "Пустыня"
    SAVANNA = "Саванна"
    STEPPE = "Степь"
    OCEAN = "Океан"
    SEA = "Море"
    MOUNTAIN = "Горы"
    
    def to_dict(self):
        return self.value
    
    @classmethod
    def from_dict(cls, value):
        for member in cls:
            if member.value == value:
                return member
        return cls.OCEAN

class Plate:
    def __init__(self, points, direction, speed, direction_name):
        self.points = points
        self.direction = direction
        self.speed = speed
        self.direction_name = direction_name
    
    def to_dict(self):
        return {
            'points': [(p.x(), p.y()) for p in self.points],
            'direction': self.direction,
            'speed': self.speed,
            'direction_name': self.direction_name
        }
    
    @classmethod
    def from_dict(cls, data):
        points = [QPointF(x, y) for x, y in data['points']]
        return cls(points, tuple(data['direction']), data['speed'], data['direction_name'])

# ------------------------------ Вспомогательные функции ------------------------------
def point_in_polygon(x, y, polygon):
    if not polygon or len(polygon) < 3:
        return False
    inside = False
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i].x(), polygon[i].y()
        x2, y2 = polygon[(i+1) % n].x(), polygon[(i+1) % n].y()
        if ((y1 > y) != (y2 > y)) and (x < (x2 - x1) * (y - y1) / (y2 - y1) + x1):
            inside = not inside
    return inside

def polygon_to_path(polygon):
    if not polygon or len(polygon) < 3:
        return None
    path = QPainterPath()
    path.addPolygon(QPolygonF(polygon))
    return path

# ------------------------------ Холст ------------------------------
class MapCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(1550, 1080)
        self.setMouseTracking(True)
        
        self.drawing_mode = "continent"
        self.current_continent_points = []
        self.continents = []
        self.continent_paths = []
        
        self.plates = []
        self.current_plate_points = None
        self.current_plate_direction = (1, 0)
        self.current_plate_speed = 1.0
        self.current_plate_direction_name = "Восток"
        
        self.height_map = None
        self.humidity_map = None
        self.temperature_map = None
        self.biome_map = None
        self.wind_map = None
        
        self.sea_level = 0.3
        self.show_biomes = False
        self.show_heightmap = False
        self.show_humidity = False
        self.show_temperature = False
        self.show_winds = False
        
        self.pan_active = False
        self.pan_start = QPoint()
        
    def set_mode(self, mode):
        self.drawing_mode = mode
        if mode == "continent":
            self.current_continent_points = []
        else:
            self.current_plate_points = []
        self.update()
        
    def set_plate_direction(self, dx, dy, name):
        self.current_plate_direction = (dx, dy)
        self.current_plate_direction_name = name
        
    def set_plate_speed(self, speed):
        self.current_plate_speed = speed
        
    def clear_all(self):
        self.current_continent_points = []
        self.continents = []
        self.continent_paths = []
        self.plates = []
        self.current_plate_points = None
        self.height_map = None
        self.humidity_map = None
        self.temperature_map = None
        self.biome_map = None
        self.wind_map = None
        self.update()
        
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = event.pos()
            if self.drawing_mode == "continent":
                self.current_continent_points = [pos]
            else:
                self.current_plate_points = [pos]
            self.update()
        elif event.button() == Qt.RightButton:
            self.pan_active = True
            self.pan_start = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            
    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            pos = event.pos()
            if self.drawing_mode == "continent" and self.current_continent_points:
                self.current_continent_points.append(pos)
                self.update()
            elif self.drawing_mode == "plate" and self.current_plate_points is not None:
                self.current_plate_points.append(pos)
                self.update()
        elif event.buttons() & Qt.RightButton and self.pan_active:
            delta = event.pos() - self.pan_start
            scroll_area = self.parent().parent()
            if isinstance(scroll_area, QScrollArea):
                h_bar = scroll_area.horizontalScrollBar()
                v_bar = scroll_area.verticalScrollBar()
                h_bar.setValue(h_bar.value() - delta.x())
                v_bar.setValue(v_bar.value() - delta.y())
            self.pan_start = event.pos()
            
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.drawing_mode == "continent" and self.current_continent_points:
                if len(self.current_continent_points) > 2:
                    self.current_continent_points.append(self.current_continent_points[0])
                self.update()
            elif self.drawing_mode == "plate" and self.current_plate_points and len(self.current_plate_points) > 2:
                self.current_plate_points.append(self.current_plate_points[0])
                plate = Plate(self.current_plate_points[:],
                              self.current_plate_direction,
                              self.current_plate_speed,
                              self.current_plate_direction_name)
                self.plates.append(plate)
                self.current_plate_points = None
                self.update()
        elif event.button() == Qt.RightButton:
            self.pan_active = False
            self.setCursor(Qt.ArrowCursor)
            
    def min_distance_to_continents(self, new_poly):
        w = self.width()
        h = self.height()
        min_dist = float('inf')
        for cont in self.continents:
            for dx in (-1, 0, 1):
                shifted = [QPointF(p.x() + dx * w, p.y()) for p in cont]
                for p1 in new_poly:
                    for p2 in shifted:
                        dist = math.hypot(p1.x() - p2.x(), p1.y() - p2.y())
                        if dist < min_dist:
                            min_dist = dist
        return min_dist
            
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(173, 216, 230))
        
        if self.biome_map is not None and self.show_biomes:
            self.draw_biome_map(painter)
        elif self.temperature_map is not None and self.show_temperature:
            self.draw_temperature_map(painter)
        elif self.humidity_map is not None and self.show_humidity:
            self.draw_humidity_map(painter)
        elif self.height_map is not None and self.show_heightmap:
            self.draw_height_map(painter)
        else:
            w = self.width()
            h = self.height()
            
            # Отрисовка материков с учётом тора (только по горизонтали)
            for cont in self.continents:
                for dx in (-1, 0, 1):
                    shifted = [QPointF(p.x() + dx * w, p.y()) for p in cont]
                    painter.setBrush(QBrush(QColor(144, 238, 144)))
                    painter.setPen(QPen(Qt.darkGreen, 2))
                    painter.drawPolygon(QPolygonF(shifted))
            
            if self.drawing_mode == "continent" and len(self.current_continent_points) > 1:
                painter.setPen(QPen(Qt.gray, 2))
                for i in range(len(self.current_continent_points)-1):
                    painter.drawLine(self.current_continent_points[i], self.current_continent_points[i+1])
            
            # Отрисовка плит с учётом тора (только по горизонтали)
            for plate in self.plates:
                for dx in (-1, 0, 1):
                    shifted = [QPointF(p.x() + dx * w, p.y()) for p in plate.points]
                    painter.setPen(QPen(Qt.red, 2))
                    painter.setBrush(Qt.NoBrush)
                    if len(shifted) > 1:
                        painter.drawPolygon(QPolygonF(shifted))
                
                # Стрелка направления (только в основном положении)
                if plate.points:
                    center = self.polygon_center(plate.points)
                    dx, dy = plate.direction
                    length = math.hypot(dx, dy)
                    if length > 0:
                        dx /= length
                        dy /= length
                    end = center + QPointF(dx * 40, dy * 40)
                    painter.setPen(QPen(Qt.red, 3))
                    painter.drawLine(center, end)
                    arrow_size = 12
                    angle = math.atan2(dy, dx)
                    p1 = end - QPointF(arrow_size * math.cos(angle + math.pi/6), arrow_size * math.sin(angle + math.pi/6))
                    p2 = end - QPointF(arrow_size * math.cos(angle - math.pi/6), arrow_size * math.sin(angle - math.pi/6))
                    painter.drawLine(end, p1)
                    painter.drawLine(end, p2)
            
            if self.drawing_mode == "plate" and self.current_plate_points and len(self.current_plate_points) > 1:
                painter.setPen(QPen(QColor(255, 165, 0), 2))
                for i in range(len(self.current_plate_points)-1):
                    painter.drawLine(self.current_plate_points[i], self.current_plate_points[i+1])
        
        if self.wind_map is not None and self.show_winds:
            self.draw_wind_map(painter)
    
    def draw_temperature_map(self, painter):
        if self.temperature_map is None:
            return
        h, w = self.temperature_map.shape
        block_size = 4
        
        for y in range(0, h, block_size):
            for x in range(0, w, block_size):
                temp = self.temperature_map[y, x]
                
                # От холодного (синий) к тёплому (красный)
                if temp < -30:
                    color = QColor(30, 30, 120)
                elif temp < -20:
                    t = (temp + 30) / 10
                    color = QColor(30 + int(t * 30), 30 + int(t * 30), 120 - int(t * 40))
                elif temp < -10:
                    t = (temp + 20) / 10
                    color = QColor(60 + int(t * 40), 60 + int(t * 40), 80 - int(t * 30))
                elif temp < 0:
                    t = (temp + 10) / 10
                    color = QColor(100 + int(t * 50), 100 + int(t * 50), 50 - int(t * 20))
                elif temp < 10:
                    t = temp / 10
                    color = QColor(150 + int(t * 50), 150 + int(t * 30), 50 - int(t * 30))
                elif temp < 20:
                    t = (temp - 10) / 10
                    color = QColor(200 + int(t * 55), 180 - int(t * 30), 50 - int(t * 20))
                elif temp < 30:
                    t = (temp - 20) / 10
                    color = QColor(255, 150 - int(t * 50), 50 - int(t * 20))
                else:
                    color = QColor(255, 50, 50)
                
                painter.fillRect(QRect(x, y, block_size, block_size), color)
    
    def draw_wind_map(self, painter):
        if self.wind_map is None:
            return
        h, w = self.wind_map.shape[:2]
        step = 45
        
        for y in range(step//2, h, step):
            for x in range(step//2, w, step):
                dx, dy, speed = self.wind_map[y, x]
                if speed > 0.01:
                    center = QPointF(x, y)
                    arrow_length = 15 + speed * 25
                    end = center + QPointF(dx * arrow_length, dy * arrow_length)
                    
                    if speed > 0.7:
                        painter.setPen(QPen(QColor(200, 50, 50), 2))
                    elif speed > 0.4:
                        painter.setPen(QPen(QColor(100, 100, 200), 2))
                    else:
                        painter.setPen(QPen(QColor(80, 80, 80), 1))
                    
                    painter.drawLine(center, end)
                    
                    angle = math.atan2(dy, dx)
                    arrow_size = 8
                    p1 = end - QPointF(arrow_size * math.cos(angle + math.pi/6), arrow_size * math.sin(angle + math.pi/6))
                    p2 = end - QPointF(arrow_size * math.cos(angle - math.pi/6), arrow_size * math.sin(angle - math.pi/6))
                    painter.drawLine(end, p1)
                    painter.drawLine(end, p2)
                    
    def draw_humidity_map(self, painter):
        if self.humidity_map is None:
            return
        h, w = self.humidity_map.shape
        block_size = 4
        
        for y in range(0, h, block_size):
            for x in range(0, w, block_size):
                humidity = self.humidity_map[y, x]
                
                if humidity < 0.2:
                    color = QColor(160, 120, 60)
                elif humidity < 0.35:
                    t = (humidity - 0.2) / 0.15
                    r = int(160 + t * 50)
                    g = int(120 + t * 50)
                    b = 60
                    color = QColor(r, g, b)
                elif humidity < 0.5:
                    t = (humidity - 0.35) / 0.15
                    r = int(210 - t * 30)
                    g = int(170 + t * 40)
                    b = 70
                    color = QColor(r, g, b)
                elif humidity < 0.65:
                    t = (humidity - 0.5) / 0.15
                    r = int(180 - t * 100)
                    g = int(210 - t * 30)
                    b = 80
                    color = QColor(r, g, b)
                elif humidity < 0.8:
                    t = (humidity - 0.65) / 0.15
                    r = int(80 - t * 40)
                    g = int(180 - t * 0)
                    b = 70
                    color = QColor(r, g, b)
                else:
                    color = QColor(40, 120, 40)
                
                painter.fillRect(QRect(x, y, block_size, block_size), color)
                    
    def draw_height_map(self, painter):
        if self.height_map is None:
            return
        h, w = self.height_map.shape
        block_size = 8
        for y in range(0, h, block_size):
            for x in range(0, w, block_size):
                height = self.height_map[y, x]
                if height < self.sea_level:
                    t = height / self.sea_level
                    intensity = 50 + int(t * 105)
                    color = QColor(20, 40, 80 + intensity)
                else:
                    normalized = (height - self.sea_level) / (1 - self.sea_level)
                    if normalized < 0.15:
                        green = 120 + int(normalized * 100)
                        color = QColor(60, green, 40)
                    elif normalized < 0.4:
                        t2 = (normalized - 0.15) / 0.25
                        green = 140 - int(t2 * 30)
                        brown = 60 + int(t2 * 70)
                        color = QColor(brown, green, 30)
                    elif normalized < 0.7:
                        t3 = (normalized - 0.4) / 0.3
                        brown = 100 + int(t3 * 70)
                        color = QColor(brown, int(brown * 0.7), int(brown * 0.4))
                    elif normalized < 0.9:
                        t4 = (normalized - 0.7) / 0.2
                        gray = 120 + int(t4 * 50)
                        color = QColor(gray, gray, gray)
                    else:
                        t5 = (normalized - 0.9) / 0.1
                        white_intensity = 200 + int(t5 * 55)
                        color = QColor(white_intensity, white_intensity, white_intensity)
                painter.fillRect(QRect(x, y, block_size, block_size), color)
                    
    def draw_biome_map(self, painter):
        if self.biome_map is None:
            return
        biome_colors = {
            BiomeType.TROPICAL_RAINFOREST: QColor(45, 90, 39),
            BiomeType.FOREST: QColor(60, 158, 45),
            BiomeType.TAIGA: QColor(44, 110, 42),
            BiomeType.TUNDRA: QColor(139, 166, 169),
            BiomeType.DESERT: QColor(240, 213, 140),
            BiomeType.SAVANNA: QColor(194, 178, 120),
            BiomeType.STEPPE: QColor(166, 160, 94),
            BiomeType.OCEAN: QColor(26, 61, 110),
            BiomeType.SEA: QColor(42, 93, 142),
            BiomeType.MOUNTAIN: QColor(139, 140, 122)
        }
        h, w = self.biome_map.shape
        block_size = 8
        for y in range(0, h, block_size):
            for x in range(0, w, block_size):
                biome = self.biome_map[y, x]
                if biome is not None:
                    painter.fillRect(QRect(x, y, block_size, block_size), biome_colors.get(biome, QColor(255,255,255)))
                        
    def polygon_center(self, points):
        if not points:
            return QPointF(0,0)
        x = sum(p.x() for p in points) / len(points)
        y = sum(p.y() for p in points) / len(points)
        return QPointF(x, y)
        
    def add_continent(self, polygon):
        if not polygon or len(polygon) < 3:
            return False
        if self.min_distance_to_continents(polygon) < 20:
            return False
        self.continents.append(polygon)
        self.continent_paths = [polygon_to_path(cont) for cont in self.continents]
        self.update()
        return True
        
    def is_point_on_land(self, x, y, w, h):
        for path in self.continent_paths:
            if path is None:
                continue
            for dx in (-1, 0, 1):
                px = x + dx * w
                if path.contains(QPointF(px, y)):
                    return True
        return False
        
    def set_height_map(self, hmap):
        self.height_map = hmap
        self.show_heightmap = True
        self.show_biomes = False
        self.show_humidity = False
        self.show_temperature = False
        self.show_winds = False
        self.update()
        
    def set_humidity_map(self, hmap, temp_map, wind_map):
        self.humidity_map = hmap
        self.temperature_map = temp_map
        self.wind_map = wind_map
        self.show_humidity = True
        self.show_heightmap = False
        self.show_biomes = False
        self.show_temperature = False
        self.update()
        
    def set_biome_map(self, bmap):
        self.biome_map = bmap
        self.show_biomes = True
        self.show_heightmap = False
        self.show_humidity = False
        self.show_temperature = False
        self.show_winds = False
        self.update()
    
    def set_temperature_map(self, temp_map):
        self.temperature_map = temp_map
        if self.show_temperature:
            self.update()
    
    def show_temperature_layer(self):
        self.show_temperature = True
        self.show_biomes = False
        self.show_heightmap = False
        self.show_humidity = False
        self.update()

# ------------------------------ Главное окно ------------------------------
class TerrainGeneratorApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Генератор карт местности")
        self.setFixedSize(1400, 800)
        
        self.roughness = 0.5
        self.iterations = 5
        self.epsilon = 5
        self.mountain_roughness = 0.5
        self.plate_direction = (1, 0)
        self.plate_speed = 1.0
        self.plate_direction_name = "Восток"
        self.global_temp = 25
        self.sea_level = 0.3
        
        self.trade_wind_speed = 0.8
        self.westerly_speed = 0.6
        self.polar_speed = 0.4
        
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(5,5,5,5)
        
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.canvas = MapCanvas()
        self.scroll_area.setWidget(self.canvas)
        main_layout.addWidget(self.scroll_area, stretch=3)
        
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFixedWidth(350)
        main_layout.addWidget(right_scroll)
        
        control_panel = QWidget()
        right_scroll.setWidget(control_panel)
        control_layout = QVBoxLayout(control_panel)
        control_layout.setSpacing(10)
        
        mode_group = QGroupBox("Режим работы")
        mode_layout = QVBoxLayout()
        btn_continent = QPushButton("Рисовать материк")
        btn_plate = QPushButton("Рисовать плиту")
        btn_continent.clicked.connect(lambda: self.canvas.set_mode("continent"))
        btn_plate.clicked.connect(lambda: self.canvas.set_mode("plate"))
        mode_layout.addWidget(btn_continent)
        mode_layout.addWidget(btn_plate)
        mode_group.setLayout(mode_layout)
        control_layout.addWidget(mode_group)
        
        plate_group = QGroupBox("Движение плиты")
        plate_layout = QVBoxLayout()
        plate_layout.addWidget(QLabel("Направление:"))
        dir_grid = QGridLayout()
        directions = [
            (0, -1, "Север", 0, 1),
            (1, -1, "Северо-восток", 0, 2),
            (1, 0, "Восток", 1, 2),
            (1, 1, "Юго-восток", 2, 2),
            (0, 1, "Юг", 2, 1),
            (-1, 1, "Юго-запад", 2, 0),
            (-1, 0, "Запад", 1, 0),
            (-1, -1, "Северо-запад", 0, 0)
        ]
        for dx, dy, name, row, col in directions:
            btn = QPushButton(name)
            btn.clicked.connect(lambda checked, dx=dx, dy=dy, name=name: self.set_plate_direction(dx, dy, name))
            dir_grid.addWidget(btn, row, col)
        plate_layout.addLayout(dir_grid)
        
        plate_layout.addWidget(QLabel("Скорость плит (влияет на высоту гор!):"))
        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setRange(5, 30)
        self.speed_slider.setValue(10)
        self.speed_slider.valueChanged.connect(self.on_speed_changed)
        plate_layout.addWidget(self.speed_slider)
        self.speed_label = QLabel("1.0")
        plate_layout.addWidget(self.speed_label)
        plate_group.setLayout(plate_layout)
        control_layout.addWidget(plate_group)
        
        wind_group = QGroupBox("Настройки ветров (влияют на влажность!)")
        wind_layout = QVBoxLayout()
        
        wind_layout.addWidget(QLabel("Пассаты (тропики):"))
        self.trade_slider = QSlider(Qt.Horizontal)
        self.trade_slider.setRange(0, 100)
        self.trade_slider.setValue(80)
        self.trade_slider.valueChanged.connect(self.on_trade_wind_changed)
        wind_layout.addWidget(self.trade_slider)
        self.trade_label = QLabel("80%")
        wind_layout.addWidget(self.trade_label)
        
        wind_layout.addWidget(QLabel("Западные ветры (умеренные):"))
        self.westerly_slider = QSlider(Qt.Horizontal)
        self.westerly_slider.setRange(0, 100)
        self.westerly_slider.setValue(60)
        self.westerly_slider.valueChanged.connect(self.on_westerly_changed)
        wind_layout.addWidget(self.westerly_slider)
        self.westerly_label = QLabel("60%")
        wind_layout.addWidget(self.westerly_label)
        
        wind_layout.addWidget(QLabel("Полярные ветры:"))
        self.polar_slider = QSlider(Qt.Horizontal)
        self.polar_slider.setRange(0, 100)
        self.polar_slider.setValue(40)
        self.polar_slider.valueChanged.connect(self.on_polar_changed)
        wind_layout.addWidget(self.polar_slider)
        self.polar_label = QLabel("40%")
        wind_layout.addWidget(self.polar_label)
        
        wind_group.setLayout(wind_layout)
        control_layout.addWidget(wind_group)
        
        params_group = QGroupBox("Параметры")
        params_layout = QVBoxLayout()
        params_layout.addWidget(QLabel("Шероховатость:"))
        self.roughness_slider = QSlider(Qt.Horizontal)
        self.roughness_slider.setRange(10, 100)
        self.roughness_slider.setValue(50)
        self.roughness_slider.valueChanged.connect(lambda v: setattr(self, 'roughness', v/100))
        params_layout.addWidget(self.roughness_slider)
        
        params_layout.addWidget(QLabel("Глубина рекурсии:"))
        self.iter_spin = QSpinBox()
        self.iter_spin.setRange(1, 8)
        self.iter_spin.setValue(5)
        self.iter_spin.valueChanged.connect(lambda v: setattr(self, 'iterations', v))
        params_layout.addWidget(self.iter_spin)
        
        params_layout.addWidget(QLabel("Уровень моря:"))
        self.sea_slider = QSlider(Qt.Horizontal)
        self.sea_slider.setRange(10, 70)
        self.sea_slider.setValue(30)
        self.sea_slider.valueChanged.connect(self.on_sea_level_changed)
        params_layout.addWidget(self.sea_slider)
        
        params_layout.addWidget(QLabel("Глобальная температура:"))
        self.temp_slider = QSlider(Qt.Horizontal)
        self.temp_slider.setRange(-40, 40)
        self.temp_slider.setValue(25)
        self.temp_slider.valueChanged.connect(self.on_global_temp_changed)
        params_layout.addWidget(self.temp_slider)
        self.temp_label = QLabel("25°C")
        params_layout.addWidget(self.temp_label)
        
        params_group.setLayout(params_layout)
        control_layout.addWidget(params_group)
        
        actions_group = QGroupBox("Действия")
        actions_layout = QVBoxLayout()
        btn_clear = QPushButton("Очистить всё")
        btn_gen_cont = QPushButton("1. Сгенерировать материк")
        btn_gen_height = QPushButton("2. Создать карту высот")
        btn_gen_humidity = QPushButton("3. Создать карту влажности")
        btn_gen_biomes = QPushButton("4. Создать биомы")
        btn_gen_temperature = QPushButton("Обновить карту температур")
        btn_show_full = QPushButton("Показать биомы")
        btn_show_humidity = QPushButton("Показать влажность")
        btn_show_height = QPushButton("Показать высоты")
        btn_show_temperature = QPushButton("Показать температуру")
        btn_show_winds = QPushButton("Показать ветра")
        btn_save = QPushButton("Сохранить карту")
        btn_load = QPushButton("Загрузить карту")
        
        btn_clear.clicked.connect(self.clear_all)
        btn_gen_cont.clicked.connect(self.generate_continent)
        btn_gen_height.clicked.connect(self.generate_heightmap)
        btn_gen_humidity.clicked.connect(self.generate_humidity_map)
        btn_gen_biomes.clicked.connect(self.generate_biomes)
        btn_gen_temperature.clicked.connect(self.generate_temperature_map)
        btn_show_full.clicked.connect(self.show_full_map)
        btn_show_humidity.clicked.connect(self.show_humidity_map)
        btn_show_height.clicked.connect(self.show_height_map)
        btn_show_temperature.clicked.connect(self.show_temperature_map)
        btn_show_winds.clicked.connect(self.show_winds)
        btn_save.clicked.connect(self.save_map)
        btn_load.clicked.connect(self.load_map)
        
        actions_layout.addWidget(btn_clear)
        actions_layout.addWidget(btn_gen_cont)
        actions_layout.addWidget(btn_gen_height)
        actions_layout.addWidget(btn_gen_humidity)
        actions_layout.addWidget(btn_gen_biomes)
        actions_layout.addWidget(btn_gen_temperature)
        actions_layout.addWidget(btn_show_full)
        actions_layout.addWidget(btn_show_humidity)
        actions_layout.addWidget(btn_show_height)
        actions_layout.addWidget(btn_show_temperature)
        actions_layout.addWidget(btn_show_winds)
        actions_layout.addWidget(btn_save)
        actions_layout.addWidget(btn_load)
        actions_group.setLayout(actions_layout)
        control_layout.addWidget(actions_group)
        
        info_group = QGroupBox("Инструкция")
        info_text = QLabel(
            "1. Нарисуйте материк (замкнутую линию)\n"
            "2. Нажмите 'Сгенерировать материк'\n"
            "3. Нарисуйте 2+ литосферные плиты\n"
            "4. Настройте СКОРОСТЬ ПЛИТ (влияет на высоту гор!)\n"
            "5. Нажмите 'Создать карту высот'\n"
            "6. Настройте скорость ветров\n"
            "7. Нажмите 'Создать карту влажности'\n"
            "8. Нажмите 'Создать биомы'\n\n"
            "Карта соединяется ТОЛЬКО по горизонтали (лево-право)\n"
            "Температура: Экватор = глобальная, Полюса = глобальная - 40°C\n\n"
            "СОХРАНЕНИЕ: сохраняет все карты и настройки в JSON\n"
            "ЗАГРУЗКА: загружает ранее сохранённую карту\n\n"
            "ПКМ + перетаскивание - перемещение"
        )
        info_text.setWordWrap(True)
        info_layout = QVBoxLayout()
        info_layout.addWidget(info_text)
        info_group.setLayout(info_layout)
        control_layout.addWidget(info_group)
        
        self.status_label = QLabel("Готов. Режим: рисование материка")
        self.status_label.setFrameStyle(QFrame.Sunken)
        control_layout.addWidget(self.status_label)
        control_layout.addStretch()
    
    # ------------------------------ ФУНКЦИЯ КОЭФФИЦИЕНТА ИСКАЖЕНИЯ ПО ШИРОТЕ ------------------------------
    def get_distortion_factor(self, y, h):
        center_y = h / 2
        lat_norm = abs(y - center_y) / center_y
        distortion = 1.0 - lat_norm * 0.6
        return max(0.4, min(1.0, distortion))
    
    # ------------------------------ СОХРАНЕНИЕ И ЗАГРУЗКА ------------------------------
    
    def save_map(self):
        if self.canvas.height_map is None:
            QMessageBox.warning(self, "Предупреждение", "Нет созданной карты для сохранения!")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(self, "Сохранить карту", "", "JSON files (*.json);;All Files (*)")
        if not file_path:
            return
        
        if not file_path.endswith('.json'):
            file_path += '.json'
        
        try:
            save_data = {
                'version': '1.0',
                'settings': {
                    'roughness': self.roughness,
                    'iterations': self.iterations,
                    'epsilon': self.epsilon,
                    'mountain_roughness': self.mountain_roughness,
                    'plate_speed': self.plate_speed,
                    'global_temp': self.global_temp,
                    'sea_level': self.sea_level,
                    'trade_wind_speed': self.trade_wind_speed,
                    'westerly_speed': self.westerly_speed,
                    'polar_speed': self.polar_speed
                },
                'continents': [[(p.x(), p.y()) for p in cont] for cont in self.canvas.continents],
                'plates': [plate.to_dict() for plate in self.canvas.plates],
            }
            
            if self.canvas.height_map is not None:
                save_data['height_map'] = self.canvas.height_map.tolist()
            
            if self.canvas.humidity_map is not None:
                save_data['humidity_map'] = self.canvas.humidity_map.tolist()
            
            if self.canvas.biome_map is not None:
                biome_map_data = [[b.value if b is not None else None for b in row] for row in self.canvas.biome_map]
                save_data['biome_map'] = biome_map_data
            
            if self.canvas.temperature_map is not None:
                save_data['temperature_map'] = self.canvas.temperature_map.tolist()
            
            if self.canvas.wind_map is not None:
                save_data['wind_map'] = self.canvas.wind_map.tolist()
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2)
            
            QMessageBox.information(self, "Сохранение", f"Карта успешно сохранена в {file_path}")
            self.status_label.setText(f"Карта сохранена: {file_path}")
            
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить карту:\n{str(e)}")
    
    def load_map(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Загрузить карту", "", "JSON files (*.json);;All Files (*)")
        if not file_path:
            return
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                load_data = json.load(f)
            
            self.clear_all()
            
            settings = load_data.get('settings', {})
            self.roughness = settings.get('roughness', self.roughness)
            self.iterations = settings.get('iterations', self.iterations)
            self.epsilon = settings.get('epsilon', self.epsilon)
            self.mountain_roughness = settings.get('mountain_roughness', self.mountain_roughness)
            self.plate_speed = settings.get('plate_speed', self.plate_speed)
            self.global_temp = settings.get('global_temp', self.global_temp)
            self.sea_level = settings.get('sea_level', self.sea_level)
            self.trade_wind_speed = settings.get('trade_wind_speed', self.trade_wind_speed)
            self.westerly_speed = settings.get('westerly_speed', self.westerly_speed)
            self.polar_speed = settings.get('polar_speed', self.polar_speed)
            
            self.roughness_slider.setValue(int(self.roughness * 100))
            self.iter_spin.setValue(self.iterations)
            self.speed_slider.setValue(int(self.plate_speed * 10))
            self.speed_label.setText(f"{self.plate_speed:.1f}")
            self.temp_slider.setValue(self.global_temp)
            self.temp_label.setText(f"{self.global_temp}°C")
            self.sea_slider.setValue(int(self.sea_level * 100))
            self.trade_slider.setValue(int(self.trade_wind_speed * 100))
            self.westerly_slider.setValue(int(self.westerly_speed * 100))
            self.polar_slider.setValue(int(self.polar_speed * 100))
            
            continents_data = load_data.get('continents', [])
            for cont_data in continents_data:
                polygon = [QPointF(x, y) for x, y in cont_data]
                self.canvas.continents.append(polygon)
            self.canvas.continent_paths = [polygon_to_path(cont) for cont in self.canvas.continents]
            
            plates_data = load_data.get('plates', [])
            for plate_data in plates_data:
                plate = Plate.from_dict(plate_data)
                self.canvas.plates.append(plate)
            
            if 'height_map' in load_data:
                height_data = np.array(load_data['height_map'], dtype=np.float32)
                self.canvas.height_map = height_data
                self.canvas.show_heightmap = True
            
            if 'humidity_map' in load_data:
                humidity_data = np.array(load_data['humidity_map'], dtype=np.float32)
                self.humidity_map = humidity_data
                self.canvas.humidity_map = humidity_data
            
            if 'biome_map' in load_data:
                biome_data = load_data['biome_map']
                biome_map = np.zeros((len(biome_data), len(biome_data[0]) if biome_data else 0), dtype=object)
                for y, row in enumerate(biome_data):
                    for x, val in enumerate(row):
                        if val is not None:
                            biome_map[y, x] = BiomeType.from_dict(val)
                self.canvas.biome_map = biome_map
            
            if 'temperature_map' in load_data:
                self.canvas.temperature_map = np.array(load_data['temperature_map'], dtype=np.float32)
            
            if 'wind_map' in load_data:
                wind_data = load_data['wind_map']
                self.canvas.wind_map = np.array(wind_data, dtype=np.float32)
            
            self.canvas.sea_level = self.sea_level
            self.canvas.update()
            
            QMessageBox.information(self, "Загрузка", f"Карта успешно загружена из {file_path}")
            self.status_label.setText(f"Карта загружена: {file_path}")
            
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить карту:\n{str(e)}")
    
    def on_trade_wind_changed(self, value):
        self.trade_wind_speed = value / 100
        self.trade_label.setText(f"{value}%")
        
    def on_westerly_changed(self, value):
        self.westerly_speed = value / 100
        self.westerly_label.setText(f"{value}%")
        
    def on_polar_changed(self, value):
        self.polar_speed = value / 100
        self.polar_label.setText(f"{value}%")
        
    def on_global_temp_changed(self, value):
        self.global_temp = value
        self.temp_label.setText(f"{value}°C")
        
    def generate_temperature_map(self):
        """Отдельная кнопка для перегенерации карты температур"""
        if self.canvas.height_map is None:
            QMessageBox.warning(self, "Предупреждение", "Сначала создайте карту высот!")
            return
        
        h, w = self.canvas.height_map.shape
        height_map = self.canvas.height_map
        sea_level = self.sea_level
        
        temperature_map = self.create_temperature_map(w, h, height_map, sea_level)
        self.canvas.set_temperature_map(temperature_map)
        self.status_label.setText(f"Карта температур обновлена! Экватор: {self.global_temp:.0f}°C, Полюса: {self.global_temp - 40:.0f}°C")
        
    def set_plate_direction(self, dx, dy, name):
        self.plate_direction = (dx, dy)
        self.plate_direction_name = name
        self.canvas.set_plate_direction(dx, dy, name)
        self.status_label.setText(f"Направление плиты: {name}")
        
    def on_speed_changed(self, value):
        self.plate_speed = value / 10.0
        self.speed_label.setText(f"{self.plate_speed:.1f}")
        self.canvas.set_plate_speed(self.plate_speed)
        
    def on_sea_level_changed(self, value):
        self.sea_level = value / 100.0
        self.canvas.sea_level = self.sea_level
        if self.canvas.height_map is not None:
            self.canvas.show_heightmap = True
            self.canvas.show_biomes = False
            self.canvas.show_humidity = False
            self.canvas.update()
            
    def clear_all(self):
        self.canvas.clear_all()
        self.status_label.setText("Очищено. Режим: рисование материка")
        
    def generate_continent(self):
        if len(self.canvas.current_continent_points) < 3:
            QMessageBox.warning(self, "Предупреждение", "Сначала нарисуйте материк!")
            return
        points = [(p.x(), p.y()) for p in self.canvas.current_continent_points]
        simplified = self.douglas_peucker(points, self.epsilon)
        if len(simplified) < 3:
            simplified = points
        fractal = []
        for i in range(len(simplified)-1):
            p1 = simplified[i]
            p2 = simplified[i+1]
            seg = self.displace_segment(p1, p2, self.roughness, self.iterations)
            if i == 0:
                fractal.extend(seg)
            else:
                fractal.extend(seg[1:])
        if len(fractal) < 3:
            QMessageBox.warning(self, "Ошибка", "Не удалось создать фрактальную линию.")
            return
        poly = [QPointF(x, y) for x, y in fractal]
        if not self.canvas.add_continent(poly):
            QMessageBox.warning(self, "Слишком близко", "Новый материк слишком близко к существующему.")
        else:
            self.canvas.current_continent_points = []
            self.status_label.setText(f"Материк добавлен. Всего: {len(self.canvas.continents)}")
    
    # ------------------------------ ГЕНЕРАЦИЯ ВЫСОТ ------------------------------
    def chaotic_noise(self, x, y, scale, seed=0):
        n1 = math.sin(x * scale * 0.05 + seed) * math.cos(y * scale * 0.05 + seed * 1.3)
        n2 = math.sin(x * scale * 0.12 + seed * 2) * 0.7
        n3 = math.cos(y * scale * 0.15 + seed * 1.7) * 0.7
        n4 = math.sin((x + y) * scale * 0.08) * math.cos((x - y) * scale * 0.08)
        return (n1 + n2 + n3 + n4) / 3.5
    
    def generate_heightmap(self):
        if len(self.canvas.continents) == 0:
            QMessageBox.warning(self, "Предупреждение", "Сначала нарисуйте хотя бы один материк!")
            return
        if len(self.canvas.plates) < 2:
            QMessageBox.warning(self, "Предупреждение", "Нарисуйте хотя бы две литосферные плиты!")
            return
        
        w = self.canvas.width()
        h = self.canvas.height()
        
        step = 8
        cols = w // step + 1
        rows = h // step + 1
        
        random.seed(42)
        np.random.seed(42)
        
        self.status_label.setText("Генерация карты высот...")
        QApplication.processEvents()
        
        height_map = np.zeros((rows, cols))
        
        for y in range(rows):
            world_y = y * step
            distortion = self.get_distortion_factor(world_y, h)
            
            for x in range(cols):
                world_x = x * step
                if self.canvas.is_point_on_land(world_x, world_y, w, h):
                    noise = self.perlin_noise(world_x / 150, world_y / 150)
                    chaotic = self.chaotic_noise(world_x, world_y, 0.5) * 0.1
                    height_map[y, x] = (0.35 + noise * 0.15 + chaotic) * distortion
                else:
                    height_map[y, x] = 0.1 * distortion
        
        self.status_label.setText("Генерация карты высот... обработка тектоники")
        QApplication.processEvents()
        
        plate_edges = []
        for plate in self.canvas.plates:
            edges = []
            points = plate.points
            if len(points) < 3:
                continue
            for i in range(len(points) - 1):
                p1 = points[i]
                p2 = points[i + 1]
                edges.append((p1, p2))
            plate_edges.append((plate, edges))
        
        mountain_influence = np.zeros((rows, cols))
        trench_influence = np.zeros((rows, cols))
        
        for y in range(rows):
            world_y = y * step
            distortion = self.get_distortion_factor(world_y, h)
            
            for x in range(cols):
                world_x = x * step
                if height_map[y, x] < 0.2:
                    continue
                
                for i, (plate1, edges1) in enumerate(plate_edges):
                    for j, (plate2, edges2) in enumerate(plate_edges):
                        if i >= j:
                            continue
                        
                        dir1 = plate1.direction
                        dir2 = plate2.direction
                        dot = dir1[0] * dir2[0] + dir1[1] * dir2[1]
                        approach = (1 - dot) / 2
                        divergence = (dot + 1) / 2
                        
                        speed_factor = (plate1.speed + plate2.speed) / 2
                        base_speed = max(0.3, min(2.0, speed_factor))
                        
                        dist_threshold = 30 + base_speed * 25
                        
                        min_dist1 = self.min_distance_to_edges(world_x, world_y, edges1, w, h)
                        min_dist2 = self.min_distance_to_edges(world_x, world_y, edges2, w, h)
                        
                        if min_dist1 < dist_threshold and min_dist2 < dist_threshold:
                            dist_factor = max(1 - min_dist1/dist_threshold, 1 - min_dist2/dist_threshold)
                            height_multiplier = 0.4 + base_speed * 0.4
                            
                            if approach > 0.35:
                                intensity = approach * base_speed * dist_factor
                                mountain_influence[y, x] = max(mountain_influence[y, x], 
                                                              min(0.85, intensity * height_multiplier * 1.2 * distortion))
                            
                            if divergence > 0.35:
                                intensity = divergence * base_speed * dist_factor
                                trench_influence[y, x] = max(trench_influence[y, x], 
                                                            min(0.45, intensity * height_multiplier * distortion))
        
        mountain_influence = self.gaussian_blur(mountain_influence, 2 + int(self.plate_speed * 2))
        trench_influence = self.gaussian_blur(trench_influence, 2)
        
        for y in range(rows):
            world_y = y * step
            distortion = self.get_distortion_factor(world_y, h)
            
            for x in range(cols):
                if mountain_influence[y, x] > 0.05:
                    new_height = 0.45 + mountain_influence[y, x] * (0.5 + self.plate_speed * 0.2)
                    height_map[y, x] = max(height_map[y, x], new_height * distortion)
                if trench_influence[y, x] > 0.05:
                    height_map[y, x] = max(0.1, height_map[y, x] - trench_influence[y, x] * 0.35)
        
        for y in range(rows):
            for x in range(cols):
                if height_map[y, x] >= self.sea_level:
                    normalized = (height_map[y, x] - self.sea_level) / (1 - self.sea_level)
                    enhanced = normalized ** 1.25
                    height_map[y, x] = self.sea_level + enhanced * (1 - self.sea_level)
        
        self.status_label.setText("Генерация карты высот... интерполяция")
        QApplication.processEvents()
        
        smoothed_low = self.gaussian_blur(height_map, 2)
        
        full_height_map = np.zeros((h, w))
        for y in range(h):
            src_y = y / step
            y0 = int(src_y)
            if y0 >= rows - 1:
                y0 = rows - 2
            fy = src_y - y0
            for x in range(w):
                src_x = x / step
                x0 = int(src_x)
                if x0 >= cols - 1:
                    x0 = cols - 2
                fx = src_x - x0
                
                v00 = smoothed_low[y0, x0]
                v10 = smoothed_low[y0, x0 + 1]
                v01 = smoothed_low[y0 + 1, x0]
                v11 = smoothed_low[y0 + 1, x0 + 1]
                
                v0 = v00 * (1 - fx) + v10 * fx
                v1 = v01 * (1 - fx) + v11 * fx
                full_height_map[y, x] = v0 * (1 - fy) + v1 * fy
        
        full_height_map = self.gaussian_blur(full_height_map, 2)
        full_height_map = np.clip(full_height_map, 0.05, 0.98)
        
        self.canvas.set_height_map(full_height_map)
        self.status_label.setText(f"Карта высот создана! Скорость плит: {self.plate_speed:.1f}, макс. высота: {full_height_map.max():.2f}")
    
    def min_distance_to_edges(self, x, y, edges, world_w, world_h):
        min_dist = float('inf')
        for p1, p2 in edges:
            for dx in (-1, 0, 1):
                x1 = p1.x() + dx * world_w
                y1 = p1.y()
                x2 = p2.x() + dx * world_w
                y2 = p2.y()
                dist = self.point_to_segment_distance(x, y, x1, y1, x2, y2)
                if dist < min_dist:
                    min_dist = dist
        return min_dist
    
    def gaussian_blur(self, array, radius):
        if radius < 1:
            return array
        result = array.copy()
        h, w = array.shape
        for _ in range(radius):
            temp = result.copy()
            for y in range(1, h - 1):
                for x in range(1, w - 1):
                    temp[y, x] = (result[y-1, x-1] + result[y-1, x] + result[y-1, x+1] +
                                  result[y, x-1] + result[y, x] + result[y, x+1] +
                                  result[y+1, x-1] + result[y+1, x] + result[y+1, x+1]) / 9
            result = temp
        return result
    
    # ------------------------------ ГЕНЕРАЦИЯ ВЛАЖНОСТИ ------------------------------
    
    def create_wind_map(self, w, h):
        wind = np.zeros((h, w, 3))
        center_y = h / 2
        
        for y in range(h):
            lat = (y - center_y) / center_y
            abs_lat = abs(lat)
            
            for x in range(w):
                if abs_lat < 0.35:
                    if lat > 0:
                        dx = -0.85
                        dy = 0.85
                        speed = self.trade_wind_speed
                    else:
                        dx = 0.85
                        dy = -0.85
                        speed = self.trade_wind_speed
                elif abs_lat < 0.7:
                    if lat > 0:
                        dx = -0.7
                        dy = 0.7
                        speed = self.westerly_speed
                    else:
                        dx = -0.7
                        dy = -0.7
                        speed = self.westerly_speed
                else:
                    if lat > 0:
                        dx = 0.6
                        dy = -0.8
                        speed = self.polar_speed
                    else:
                        dx = 0.6
                        dy = 0.8
                        speed = self.polar_speed
                
                length = math.hypot(dx, dy)
                if length > 0:
                    dx /= length
                    dy /= length
                
                wind[y, x] = [dx, dy, speed]
        
        return wind
    
    def create_temperature_map(self, w, h, height_map, sea_level):
        """
        Создаёт карту температур.
        Экватор (центр) = глобальная температура
        Полюса (верх/низ) = глобальная температура - 40
        """
        temp = np.zeros((h, w))
        center_y = h / 2
        
        for y in range(h):
            # Широтный фактор (0.0 на полюсах, 1.0 на экваторе)
            # Чем дальше от экватора, тем холоднее
            lat_factor = 1 - abs(y - center_y) / center_y
            # Квадратичная зависимость для более резкого перепада
            lat_factor = lat_factor ** 1.2
            
            # Температура от широты: на экваторе = global_temp, на полюсах = global_temp - 40
            base_temp = self.global_temp - (1 - lat_factor) * 40
            
            for x in range(w):
                # Высотный фактор (холоднее в горах)
                height = height_map[y, x]
                if height < sea_level:
                    height_factor = 1.0
                else:
                    normalized_height = (height - sea_level) / (1 - sea_level)
                    height_factor = 1 - normalized_height * 0.5
                
                t = base_temp * height_factor
                temp[y, x] = np.clip(t, -50, 50)
        
        return temp
    
    def distance_to_water_smooth(self, height_map, sea_level):
        h, w = height_map.shape
        distance = np.full((h, w), 500.0)
        
        water_pixels = []
        step = 8
        for y in range(0, h, step):
            for x in range(0, w, step):
                if height_map[y, x] < sea_level:
                    water_pixels.append((x, y))
        
        for y in range(0, h, step):
            for x in range(0, w, step):
                if height_map[y, x] >= sea_level:
                    min_dist = 500
                    for wx, wy in water_pixels:
                        dist = math.hypot(x - wx, y - wy)
                        if dist < min_dist:
                            min_dist = dist
                    distance[y, x] = min_dist
        
        result = np.zeros((h, w))
        for y in range(h):
            for x in range(w):
                yy = (y // step) * step
                xx = (x // step) * step
                if yy >= h:
                    yy = h - step
                if xx >= w:
                    xx = w - step
                result[y, x] = distance[yy, xx]
        
        result = self.gaussian_blur(result, 2)
        return result
    
    def calculate_rain_shadow_with_speed(self, x, y, wind_map, height_map, sea_level):
        dx, dy, wind_speed = wind_map[y, x]
        
        steps = 40
        path_has_mountain = False
        path_has_water = False
        mountain_height_factor = 0
        
        for step in range(1, steps + 1):
            px = int(x - dx * step * 2)
            py = int(y - dy * step * 2)
            
            if px < 0 or px >= height_map.shape[1] or py < 0 or py >= height_map.shape[0]:
                break
            
            height = height_map[py, px]
            
            if height < sea_level:
                path_has_water = True
            
            if height > 0.65 and not path_has_mountain:
                path_has_mountain = True
                mountain_height_factor = min(1.0, (height - 0.65) / 0.3)
        
        wind_boost = 0.5 + wind_speed * 1.0
        
        if path_has_mountain:
            if path_has_water:
                return (0.9 + mountain_height_factor * 0.3) * wind_boost
            else:
                return max(0.2, (0.4 - mountain_height_factor * 0.2)) * (1 - wind_speed * 0.1)
        elif path_has_water:
            return 1.0 * wind_boost
        else:
            return 0.7
    
    def generate_humidity_map(self):
        if self.canvas.height_map is None:
            QMessageBox.warning(self, "Предупреждение", "Сначала создайте карту высот!")
            return
        
        h, w = self.canvas.height_map.shape
        height_map = self.canvas.height_map
        sea_level = self.sea_level
        
        self.status_label.setText("Создание карты ветров...")
        QApplication.processEvents()
        
        wind_map = self.create_wind_map(w, h)
        
        self.status_label.setText("Создание карты температур...")
        QApplication.processEvents()
        
        temperature_map = self.create_temperature_map(w, h, height_map, sea_level)
        self.canvas.temperature_map = temperature_map
        
        self.status_label.setText("Вычисление расстояния до воды...")
        QApplication.processEvents()
        
        water_distance = self.distance_to_water_smooth(height_map, sea_level)
        
        self.status_label.setText("Расчёт влажности...")
        QApplication.processEvents()
        
        humidity_map = np.zeros((h, w))
        step = 6
        
        for y in range(0, h, step):
            for x in range(0, w, step):
                height = height_map[y, x]
                
                if height < sea_level:
                    humidity = 0.95
                else:
                    dist = water_distance[y, x]
                    water_factor = math.exp(-dist / 80)
                    
                    temp = temperature_map[y, x]
                    if temp > 25:
                        temp_factor = 0.9
                    elif temp > 15:
                        temp_factor = 0.7
                    elif temp > 5:
                        temp_factor = 0.5
                    else:
                        temp_factor = 0.3
                    
                    height_normalized = (height - sea_level) / (1 - sea_level)
                    height_factor = 1 - height_normalized * 0.5
                    
                    rain_factor = self.calculate_rain_shadow_with_speed(x, y, wind_map, height_map, sea_level)
                    
                    humidity = (water_factor * 0.4 + 
                               temp_factor * 0.25 + 
                               height_factor * 0.2 + 
                               rain_factor * 0.15)
                    
                    humidity = np.clip(humidity, 0.15, 0.95)
                
                for dy in range(step):
                    for dx in range(step):
                        ny, nx = y + dy, x + dx
                        if ny < h and nx < w:
                            humidity_map[ny, nx] = humidity
        
        humidity_map = self.gaussian_blur(humidity_map, 2)
        
        self.humidity_map = humidity_map
        self.canvas.set_humidity_map(humidity_map, temperature_map, wind_map)
        self.status_label.setText(f"Карта влажности создана!")
    
    def generate_biomes(self):
        if self.humidity_map is None:
            QMessageBox.warning(self, "Предупреждение", "Сначала создайте карту влажности!")
            return
        
        h, w = self.humidity_map.shape
        height_map = self.canvas.height_map
        biome_map = np.zeros((h, w), dtype=object)
        
        temperature_map = self.create_temperature_map(w, h, height_map, self.sea_level)
        self.canvas.temperature_map = temperature_map
        
        biome_counts = {b: 0 for b in BiomeType}
        
        for y in range(h):
            for x in range(w):
                height = height_map[y, x]
                
                if height < self.sea_level:
                    if height < self.sea_level - 0.15:
                        biome = BiomeType.OCEAN
                    else:
                        biome = BiomeType.SEA
                else:
                    temp = temperature_map[y, x]
                    humidity = self.humidity_map[y, x]
                    
                    if height > 0.75:
                        biome = BiomeType.MOUNTAIN
                    elif temp > 22 and humidity > 0.65:
                        biome = BiomeType.TROPICAL_RAINFOREST
                    elif temp > 18 and humidity > 0.55:
                        biome = BiomeType.FOREST
                    elif temp > 12 and humidity > 0.5:
                        biome = BiomeType.SAVANNA
                    elif temp > 5 and humidity > 0.4:
                        biome = BiomeType.STEPPE
                    elif temp > -5 and humidity > 0.35:
                        biome = BiomeType.TAIGA
                    elif temp < 0:
                        biome = BiomeType.TUNDRA
                    elif humidity < 0.25:
                        biome = BiomeType.DESERT
                    else:
                        biome = BiomeType.STEPPE
                
                biome_map[y, x] = biome
                biome_counts[biome] += 1
        
        self.canvas.set_biome_map(biome_map)
        
        # Вывод статистики биомов
        total_land = sum(biome_counts[b] for b in [BiomeType.TROPICAL_RAINFOREST, BiomeType.FOREST, BiomeType.TAIGA, 
                                                     BiomeType.TUNDRA, BiomeType.DESERT, BiomeType.SAVANNA, 
                                                     BiomeType.STEPPE, BiomeType.MOUNTAIN])
        if total_land > 0:
            stats = []
            for biome, count in biome_counts.items():
                if count > 0 and biome not in [BiomeType.OCEAN, BiomeType.SEA]:
                    stats.append(f"{biome.value}: {count/total_land*100:.1f}%")
            self.status_label.setText(f"Карта биомов создана! | " + " | ".join(stats[:6]))
        else:
            self.status_label.setText("Карта биомов создана! (нет суши)")
    
    def show_temperature_map(self):
        if self.canvas.temperature_map is not None:
            self.canvas.show_temperature = True
            self.canvas.show_biomes = False
            self.canvas.show_heightmap = False
            self.canvas.show_humidity = False
            self.canvas.show_winds = False
            self.canvas.update()
        else:
            QMessageBox.warning(self, "Предупреждение", "Сначала создайте карту температур!")
    
    # ------------------------------ ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ------------------------------
    def douglas_peucker(self, points, epsilon):
        if len(points) < 3:
            return points[:]
        first, last = points[0], points[-1]
        max_dist = 0
        index = 0
        for i in range(1, len(points)-1):
            dist = self.point_line_distance(points[i], first, last)
            if dist > max_dist:
                max_dist = dist
                index = i
        if max_dist > epsilon:
            left = self.douglas_peucker(points[:index+1], epsilon)
            right = self.douglas_peucker(points[index:], epsilon)
            return left[:-1] + right
        else:
            return [first, last]
    
    def point_line_distance(self, point, line_start, line_end):
        x0, y0 = point
        x1, y1 = line_start
        x2, y2 = line_end
        if x1 == x2 and y1 == y2:
            return math.hypot(x0 - x1, y0 - y1)
        numerator = abs((x2 - x1) * (y1 - y0) - (x1 - x0) * (y2 - y1))
        denominator = math.hypot(x2 - x1, y2 - y1)
        return numerator / denominator
    
    def displace_segment(self, p1, p2, roughness, iterations):
        if iterations <= 0 or roughness < 0.01:
            return [p1, p2]
        mid_x = (p1[0] + p2[0]) / 2
        mid_y = (p1[1] + p2[1]) / 2
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        length = math.hypot(dx, dy)
        if length < 1e-6:
            return [p1, p2]
        perp_x = -dy / length
        perp_y = dx / length
        max_shift = length * roughness
        shift = random.uniform(-max_shift, max_shift)
        displaced_x = mid_x + perp_x * shift
        displaced_y = mid_y + perp_y * shift
        left = self.displace_segment(p1, (displaced_x, displaced_y), roughness * 0.6, iterations - 1)
        right = self.displace_segment((displaced_x, displaced_y), p2, roughness * 0.6, iterations - 1)
        return left[:-1] + right
    
    def point_to_segment_distance(self, px, py, x1, y1, x2, y2):
        dx = x2 - x1
        dy = y2 - y1
        if dx == 0 and dy == 0:
            return math.hypot(px - x1, py - y1)
        t = ((px - x1) * dx + (py - y1) * dy) / (dx*dx + dy*dy)
        if t < 0:
            return math.hypot(px - x1, py - y1)
        elif t > 1:
            return math.hypot(px - x2, py - y2)
        else:
            proj_x = x1 + t * dx
            proj_y = y1 + t * dy
            return math.hypot(px - proj_x, py - proj_y)
    
    def perlin_noise(self, x, y):
        return (math.sin(x * 0.1) * math.cos(y * 0.1) +
                math.sin(x * 0.3 + 1) * math.cos(y * 0.3 + 1) * 0.5 +
                math.sin(x * 0.7 + 2) * math.cos(y * 0.7 + 2) * 0.25) / 1.75 + 0.5
    
    def show_full_map(self):
        if self.canvas.biome_map is not None:
            self.canvas.show_biomes = True
            self.canvas.show_heightmap = False
            self.canvas.show_humidity = False
            self.canvas.show_temperature = False
            self.canvas.show_winds = False
            self.canvas.update()
        elif self.canvas.height_map is not None:
            self.show_height_map()
            
    def show_humidity_map(self):
        if self.humidity_map is not None:
            self.canvas.show_humidity = True
            self.canvas.show_biomes = False
            self.canvas.show_heightmap = False
            self.canvas.show_temperature = False
            self.canvas.show_winds = False
            self.canvas.update()
        else:
            QMessageBox.warning(self, "Предупреждение", "Сначала создайте карту влажности!")
            
    def show_height_map(self):
        if self.canvas.height_map is not None:
            self.canvas.show_heightmap = True
            self.canvas.show_biomes = False
            self.canvas.show_humidity = False
            self.canvas.show_temperature = False
            self.canvas.show_winds = False
            self.canvas.update()
        else:
            QMessageBox.warning(self, "Предупреждение", "Сначала создайте карту высот!")
            
    def show_winds(self):
        if self.canvas.wind_map is not None:
            self.canvas.show_winds = not self.canvas.show_winds
            self.canvas.update()
        else:
            QMessageBox.warning(self, "Предупреждение", "Сначала создайте карту влажности!")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TerrainGeneratorApp()
    window.show()
    sys.exit(app.exec_())