import math

def calculate_arch(x: float, peak: float, shape: str) -> float:
    if shape == "parabolic":
        return -4 * (x - peak)**2 + 1
    elif shape == "cosine":
        # Cosine arch: peak at x=peak. 
        # If x=peak, cos(0) = 1.
        # If peak is 0.5, cos((x-0.5)*2*pi) ... wait, we want it to be 1 at peak, and go down.
        # Let's just use math.cos((x - peak) * math.pi)
        return math.cos((x - peak) * math.pi)
    elif shape == "flat":
        return 0.0
    elif shape == "inverted":
        return -(-4 * (x - peak)**2 + 1)
    elif shape == "asymmetric-Bezier":
        # simple asymmetric curve
        return -4 * (x - peak)**2 + 1 # Just a placeholder
    return 0.0

print(calculate_arch(0, 0.6, "parabolic"))
print(calculate_arch(0.6, 0.6, "parabolic"))
print(calculate_arch(1, 0.6, "parabolic"))
