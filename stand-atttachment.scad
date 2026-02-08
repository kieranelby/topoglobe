$fn = 60;
height = 18;
th = 5;
bbh = 1;
bh = 5;
mh = height - th - bh - bbh;
hr = 3.6;
bbr = 6.75;
br = 7.25;
mr = 5.5;
tr = 6.5;
eps = 0.01;
difference() {
    union() {
        translate([0,0,bbh/2]) {
            cylinder(h = bbh, r1 = bbr, r2 = br, center = true);
        }
        translate([0,0,bbh + bh/2]) {
            cylinder(h = bh, r = br, center = true);
        }
        translate([0,0,bbh + bh + mh/2]) {
            cylinder(h = mh, r1 = br, r2 = mr, center = true);
        }
        translate([0,0,bbh + bh + mh + th/2]) {
            cylinder(h = th, r1 = mr, r2 = tr, center = true);
        }
    }
    translate([0, 0, height/2]) {
        cylinder(h = height + 2*eps, r = hr, center = true);
    }
}

