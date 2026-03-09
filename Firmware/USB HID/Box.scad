// ESP32-S3 Rev TFT Switch Interface Enclosure
// Includes space for Feather board, LiPo battery, and 2x 3.5mm jacks
// Xbox Adaptive Controller inspired design

$fn = 60; // Smooth curves

// ===== PARAMETERS =====
// Main enclosure
box_length = 100;
box_width = 75;
box_height = 30;
wall_thickness = 2.5;
corner_radius = 8;

// Component dimensions
feather_length = 51;
feather_width = 23;
feather_height = 8;  // Including components

// LiPo battery (standard 500-1000mAh size)
battery_length = 50;
battery_width = 30;
battery_height = 6;

// Display window (centered on top)
display_x = 30;  // Width
display_y = 17;  // Height
display_offset_from_top = 12;  // Distance from top edge

// Jack dimensions
jack_diameter = 6.2;  // 3.5mm mono jack
jack_spacing = 30;

// USB-C port
usb_width = 10;
usb_height = 4;

// Mounting
screw_diameter = 2.5;  // M2.5 screws

// ===== BOTTOM ENCLOSURE =====
module bottom_enclosure() {
    difference() {
        // Main body
        rounded_box(box_length, box_width, box_height, corner_radius);
        
        // Hollow interior
        translate([0, 0, wall_thickness])
            rounded_box(
                box_length - wall_thickness*2, 
                box_width - wall_thickness*2, 
                box_height*2,  // Extra height for hollow
                corner_radius - wall_thickness
            );
        
        // Display window cutout (centered, upper portion)
        translate([0, box_width/2 - display_offset_from_top, box_height - wall_thickness/2])
            cube([display_x, display_y, wall_thickness*2], center=true);
        
        // Left jack hole (Navigate)
        translate([-box_length/2, jack_spacing/2, box_height/2 + 3])
            rotate([0, 90, 0])
            cylinder(h=wall_thickness*2, d=jack_diameter, center=true);
        
        // Right jack hole (Select)
        translate([box_length/2, jack_spacing/2, box_height/2 + 3])
            rotate([0, 90, 0])
            cylinder(h=wall_thickness*2, d=jack_diameter, center=true);
        
        // USB-C port (back side, offset up for board placement)
        translate([0, -box_width/2, box_height/2 + 5])
            rotate([90, 0, 0])
            rounded_rectangle(usb_width, usb_height, wall_thickness*2, 1);
        
        // JST battery connector cutout (left side, near back)
        translate([-box_length/2, -box_width/3, box_height/2])
            rotate([0, 90, 0])
            rounded_rectangle(8, 6, wall_thickness*2, 1);
        
        // Power switch cutout (right side, near back)
        translate([box_length/2, -box_width/3, box_height/2])
            rotate([0, 90, 0])
            cube([7, 4, wall_thickness*2], center=true);
        
        // Ventilation slots (bottom, for battery safety)
        for(i = [-2:2]) {
            translate([i*14, -5, -wall_thickness/2])
                cube([10, 35, wall_thickness*2], center=true);
        }
    }
    
    // === INTERNAL STRUCTURES ===
    
    // Feather mounting posts (with screw holes)
    translate([-feather_length/2 + 5, box_width/4, wall_thickness]) {
        mounting_post(3, 6, screw_diameter);  // Front left
        translate([feather_length - 10, 0, 0]) 
            mounting_post(3, 6, screw_diameter);  // Front right
    }
    
    // Battery support platform (underneath the Feather)
    translate([0, -box_width/6, wall_thickness])
        cube([battery_length + 4, battery_width + 4, 2], center=true);
    
    // Battery retention clips
    translate([battery_length/2 - 2, -box_width/6 - battery_width/2 - 1, wall_thickness + 1])
        cube([4, 2, battery_height + 2], center=true);
    translate([-battery_length/2 + 2, -box_width/6 - battery_width/2 - 1, wall_thickness + 1])
        cube([4, 2, battery_height + 2], center=true);
    
    // Display bezel (raised frame around window)
    difference() {
        translate([0, box_width/2 - display_offset_from_top, box_height - wall_thickness])
            rounded_rectangle_3d(display_x + 6, display_y + 6, 1, 2);
        translate([0, box_width/2 - display_offset_from_top, box_height - wall_thickness - 0.5])
            cube([display_x, display_y, 2], center=true);
    }
    
    // Label embossing
    translate([-box_length/2 + 15, jack_spacing/2, box_height - 1])
        linear_extrude(1.5)
        text("NAV", size=5, halign="center", font="Arial:style=Bold");
    
    translate([box_length/2 - 15, jack_spacing/2, box_height - 1])
        linear_extrude(1.5)
        text("SEL", size=5, halign="center", font="Arial:style=Bold");
}

// ===== TOP LID (OPTIONAL) =====
module top_lid() {
    difference() {
        // Lid body
        rounded_box(box_length, box_width, 3, corner_radius);
        
        // Recess for fitting into bottom
        translate([0, 0, 1.5])
            rounded_box(
                box_length - wall_thickness*3,
                box_width - wall_thickness*3,
                3,
                corner_radius - wall_thickness
            );
        
        // Label text cutout
        translate([0, 0, 1.5])
            linear_extrude(2)
            text("SWITCH INTERFACE", size=4, halign="center", valign="center", font="Arial:style=Bold");
    }
}

// ===== HELPER MODULES =====
module rounded_box(l, w, h, r) {
    hull() {
        translate([-(l/2-r), -(w/2-r), 0]) cylinder(h=h, r=r);
        translate([(l/2-r), -(w/2-r), 0]) cylinder(h=h, r=r);
        translate([-(l/2-r), (w/2-r), 0]) cylinder(h=h, r=r);
        translate([(l/2-r), (w/2-r), 0]) cylinder(h=h, r=r);
    }
}

module rounded_rectangle(w, h, depth, r) {
    linear_extrude(height=depth, center=true)
    offset(r=r)
    square([w-2*r, h-2*r], center=true);
}

module rounded_rectangle_3d(w, h, depth, r) {
    hull() {
        translate([-(w/2-r), -(h/2-r), 0]) cylinder(h=depth, r=r);
        translate([(w/2-r), -(h/2-r), 0]) cylinder(h=depth, r=r);
        translate([-(w/2-r), (h/2-r), 0]) cylinder(h=depth, r=r);
        translate([(w/2-r), (h/2-r), 0]) cylinder(h=depth, r=r);
    }
}

module mounting_post(diameter, height, hole_diameter) {
    difference() {
        cylinder(h=height, d=diameter*2);
        // Screw hole
        translate([0, 0, -0.5])
            cylinder(h=height+1, d=hole_diameter);
    }
}

// ===== ASSEMBLY VIEW =====
// Change these to print individual parts
show_bottom = true;
show_top = false;
exploded_view = false;

if (show_bottom) {
    bottom_enclosure();
}

if (show_top) {
    if (exploded_view) {
        translate([0, 0, 50])
            top_lid();
    } else {
        translate([0, 0, box_height - 3])
            top_lid();
    }
}

// For printing, render one at a time:
// 1. Set show_bottom = true, show_top = false (render bottom)
// 2. Export STL
// 3. Set show_bottom = false, show_top = true (render top)
// 4. Export STL