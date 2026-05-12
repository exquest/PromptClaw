# Cypherclaw Sample Directory Layout Specification

This document defines the standard directory layout for the Cypherclaw sample library, located at `/home/user/cypherclaw-data/samples/`.

## Directory Structure

The base path for all sample data is:
`/home/user/cypherclaw-data/samples/`

The directory is structured as follows:

```text
/home/user/cypherclaw-data/samples/
├── index.sqlite
├── library/
├── self/
├── room/
├── contact/
├── theramini/
└── keyboard/
```

## Database

* **`index.sqlite`**: The primary SQLite database file used to index all samples within the subdirectories, store metadata, tag information, and maintain relationships between samples and their sources. It must reside in the root of the `samples/` directory.

## Subdirectories and Purposes

* **`library/`**: Contains pre-curated, static sample libraries and standard soundbanks provided to Cypherclaw. These are typically read-only or infrequently updated collections used as foundational musical building blocks.
* **`self/`**: Dedicated to samples generated, synthesized, or resampled by Cypherclaw itself. This acts as an internal bounce or render directory for the agent's own creative output.
* **`room/`**: Stores audio captured from the ambient room environment (e.g., via open air microphones). This captures the acoustic ecology of the space.
* **`contact/`**: Contains audio captured specifically from contact microphones. This focuses on tactile, physical interactions and surface resonances.
* **`theramini/`**: Dedicated to recordings captured directly from the Moog Theremini or similar specialized gestural/continuous pitch instruments.
* **`keyboard/`**: Stores recordings derived from keyboard instruments or MIDI-controlled sound modules, capturing structured melodic and harmonic performances.
