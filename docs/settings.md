# Application Settings

`Custom Names` - This setting replaces the internal names with mapped ones in `defs`. 
This setting can be especially useful for if you don't know the ID of an item in a big list, allowing you to search by its display name. 
Some data, such as Nightreign garbs and Sekiro bosses, were mapped manually, but most of it was scripted from Smithbox exports.  

`Hide Blank Icons` - Only for older games with no layout system. DSTS crops the atlases in a grid layout. Because of this, some 'tiles' 
may be blank. DSTS automatically recognises these blank spaces and ignores them when building the subtexture list. Disable this setting to show 
the aforementioned blank spaces, for example, if you wanted to place a new icon in that spot.  

`Calculate Image Size` - When enabled, simulates the creation of a PNG image to display its file size. This info may be nice to know, but it comes at 
a significant performance drop. It is, therefore, disabled by default.  

`Show Icon Borders` - Draws a red bounding box around subtextures wherever possible. This will not be visible on texture dumps or replacements, 
but can be optionally enabled for atlas exports.  

`Alpha Threshold` - Any pixel with an alpha value less than or equal to this number will have their RGB values set to 0. Click to update the value.  