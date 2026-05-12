from pathlib import Path

RECIPE_NAMES = [
    "midi-to-frequency",
    "intervals",
    "scales",
    "chord-voicings",
    "swing",
    "polyrhythm",
    "subtractive",
    "fm",
    "additive",
    "granular",
    "physical-modeling",
    "spectral-freeze",
    "eq",
    "compression",
    "sidechain",
    "reverb",
    "delay",
    "master-bus",
    "groups",
    "buses",
    "patterns",
    "envelopes",
]

def test_recipe_files_exist() -> None:
    recipe_dir = Path("my-claw/curriculum/recipes/supercollider")
    assert recipe_dir.exists(), "Recipe directory does not exist"
    
    for recipe in RECIPE_NAMES:
        recipe_file = recipe_dir / f"{recipe}.md"
        assert recipe_file.exists(), f"Recipe file {recipe_file} is missing"

def test_recipe_files_contain_labels() -> None:
    recipe_dir = Path("my-claw/curriculum/recipes/supercollider")
    
    for recipe in RECIPE_NAMES:
        recipe_file = recipe_dir / f"{recipe}.md"
        if not recipe_file.exists():
            continue
            
        content = recipe_file.read_text()
        
        # We require a labels line in each recipe
        # For instance: "Labels: supercollider, recipe"
        assert "Labels: supercollider, recipe" in content, f"Recipe {recipe_file} is missing required labels"

def test_recipes_linked_in_curriculum() -> None:
    overview_102 = Path("my-claw/curriculum/EMSD-102/reference/01-overview.md")
    overview_130 = Path("my-claw/curriculum/EMSD-130/reference/01-overview.md")
    
    content_102 = overview_102.read_text()
    content_130 = overview_130.read_text()
    
    combined_content = content_102 + "\n" + content_130
    
    # We require that somewhere in these two files, there is a link to the recipes directory
    assert "recipes/supercollider" in combined_content, "Recipes directory is not discoverable from EMSD-102 or EMSD-130 reference docs"
