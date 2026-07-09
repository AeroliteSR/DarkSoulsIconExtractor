# Exporting Textures

Pressing the "Export Selected Texture" button (Fig. 5 in [Introduction](introduction.md)) will work differently depending on what you have selected.

## Atlases:
If the atlas contains subtextures, you will be prompted if you want to export the Full Atlas, or its Subtextures. Selecting the former will simply export the entire atlas as a single image file. Selecting "All Subtextures" will create cropped pngs of the atlas for every defined subtexture, writing them to a folder of the atlas' name.

If the setting "Show Icon Borders" is enabled in [settings](settings.md) and you're exporting "Full Atlas", you will also be asked if you wish to keep the borders in your export.

You will then be prompted for an output directory. This is where the files are written to.

Finally, you will be asked if you want to export as png, or if possible, dds.

## Subtextures:
Subtextures are much simpler. As the crop has to be a png file, it only asks for an output directory and promptly writes to that location.

## Dumping:
Accessible from the `File` menu. Works much the same as the above options, but exports ALL loaded textures of that type.