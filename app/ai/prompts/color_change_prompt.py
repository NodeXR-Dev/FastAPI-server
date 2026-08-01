COLOR_CHANGE_PROMPT = """
You are performing a precise color-editing task.

The first image is the original source image.
The second image is a rough color guide painted over the original image.

Edit the original image according to the color guide.

Instructions:

1. Identify only the regions that were painted or marked in the color-guide image.
2. Apply the indicated colors only to those corresponding regions in the original image.
3. Treat the painted colors as target color instructions, not as literal brush strokes.
4. Remove all visible rough brush strokes, scribbles, marker textures, and guide artifacts from the final result.
5. Preserve the original object's geometry, silhouette, proportions, details, texture, material, lighting, shadows, highlights, reflections, and depth.
6. Preserve all unmarked regions as closely as possible to the original image.
7. Do not change the camera angle, composition, framing, background, object position, or image perspective.
8. Do not add or remove objects.
9. Do not add text, logos, symbols, patterns, or decorative details.
10. Match the hue and overall color intention of the guide while adapting the color naturally to the original material and lighting.
11. Maintain realistic shading instead of replacing the region with a flat solid color.
12. Keep the original image dimensions and aspect ratio.

This is a localized color-editing task, not a redesign or full image regeneration.

Return only the edited image.
""".strip()
