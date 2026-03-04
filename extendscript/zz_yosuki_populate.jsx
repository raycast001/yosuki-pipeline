/**
 * zz_yosuki_populate.jsx — AE Startup Hook for Yosuki Pipeline
 * =============================================================
 *
 * HOW THIS WORKS (important background):
 *   aerender.exe does NOT have a "-script" flag. The "-s" flag is START FRAME.
 *   All aerender functionality is implemented in commandLineRenderer.jsx, which
 *   lives in Scripts/Startup/ and runs when AE starts.
 *
 *   This file also lives in Scripts/Startup/. It runs AFTER commandLineRenderer.jsx
 *   (because "zz_" sorts after "commandLine" alphabetically). At that point,
 *   gAECommandLineRenderer is defined but Render() hasn't been called yet.
 *
 *   We wrap AddCompToRenderQueue() — a method called by commandLineRenderer.jsx
 *   after the project is opened but before rendering begins. This gives us a
 *   hook point to modify the project in memory before the render queue is set up.
 *
 * SAFETY:
 *   The hook checks for a {projectName}_data.json file next to the .aep.
 *   If none is found, it does nothing. Normal AE operation is unaffected.
 *
 * TO INSTALL: copy this file to:
 *   C:\Program Files\Adobe\Adobe After Effects 2026\Support Files\Scripts\Startup\
 */

(function() {

    // Only hook if gAECommandLineRenderer exists (i.e., we're in aerender mode)
    if (typeof gAECommandLineRenderer === 'undefined') {
        return;
    }

    // Save the original AddCompToRenderQueue function
    var _origAddCompToRenderQueue = gAECommandLineRenderer.AddCompToRenderQueue;

    // Replace it with our wrapper
    gAECommandLineRenderer.AddCompToRenderQueue = function(comp_name) {

        // Try to run populate logic. If anything fails, don't break the render.
        try {
            yosukiPopulate();
        } catch (e) {
            $.writeln("zz_yosuki_populate.jsx: populate step threw: " + e.toString());
            // Don't stop the render — just continue with original footage
        }

        // Always call the original function to add the comp normally
        return _origAddCompToRenderQueue.call(gAECommandLineRenderer, comp_name);
    };

    $.writeln("zz_yosuki_populate.jsx: AddCompToRenderQueue hook installed.");

})();


// ─────────────────────────────────────────────
// POPULATE LOGIC
// ─────────────────────────────────────────────

function yosukiPopulate() {

    // ── Safety check: is a project open? ────────────────────────────────
    if (!app.project || !app.project.file) {
        $.writeln("yosukiPopulate: no project open, skipping.");
        return;
    }

    // ── Find the data JSON next to the .aep ─────────────────────────────
    var projectFile = app.project.file;
    var projectName = projectFile.name.replace(/\.aep$/i, "");
    var dataFile    = new File(projectFile.parent.fsName + "/" + projectName + "_data.json");

    if (!dataFile.exists) {
        $.writeln("yosukiPopulate: no data JSON found for '" + projectName + "', skipping.");
        return;  // Not a Yosuki render — leave project untouched
    }

    $.writeln("yosukiPopulate: data JSON found: " + dataFile.fsName);

    // ── Read and parse the data JSON ─────────────────────────────────────
    dataFile.encoding = "UTF-8";
    if (!dataFile.open("r")) {
        $.writeln("yosukiPopulate: ERROR — cannot open data file.");
        return;
    }
    var content = dataFile.read();
    dataFile.close();

    if (!content || content.length === 0) {
        $.writeln("yosukiPopulate: ERROR — data file is empty.");
        return;
    }

    var data;
    try {
        data = eval("(" + content + ")");
    } catch (e) {
        $.writeln("yosukiPopulate: ERROR — failed to parse JSON: " + e.toString());
        return;
    }

    $.writeln("yosukiPopulate: processing variant: " + data.variant_id);
    $.writeln("  bg_image_path:      " + data.bg_image_path);
    $.writeln("  product_image_path: " + data.product_image_path);

    // ── Write debug log file ─────────────────────────────────────────────
    var logFile = new File(projectFile.parent.fsName + "/jsx_debug.log");
    logFile.encoding = "UTF-8";
    logFile.open("w");
    logFile.writeln("=== yosukiPopulate started ===");
    logFile.writeln("variant: " + data.variant_id);
    logFile.writeln("bg_image_path: " + data.bg_image_path);
    logFile.writeln("product_image_path: " + data.product_image_path);

    // ── Find MAIN_COMP ───────────────────────────────────────────────────
    var compName = data.comp_name || "MAIN_COMP";
    var comp = null;
    for (var i = 1; i <= app.project.numItems; i++) {
        var item = app.project.item(i);
        if (item instanceof CompItem && item.name === compName) {
            comp = item;
            break;
        }
    }

    if (!comp) {
        logFile.writeln("ERROR: comp '" + compName + "' not found!");
        logFile.close();
        return;
    }

    logFile.writeln("comp found: " + comp.name + " (" + comp.numLayers + " layers)");

    // ── Dump layers for debugging ────────────────────────────────────────
    for (var li = 1; li <= comp.numLayers; li++) {
        var layer = comp.layer(li);
        var typeStr = "unknown";
        if (layer instanceof TextLayer)   { typeStr = "TEXT"; }
        else if (layer instanceof ShapeLayer) { typeStr = "SHAPE"; }
        else if (layer instanceof AVLayer) {
            if (layer.source instanceof CompItem)    { typeStr = "PRECOMP(" + layer.source.name + ")"; }
            else if (layer.source instanceof FootageItem) { typeStr = "FOOTAGE(" + layer.source.name + ")"; }
            else { typeStr = "SOLID"; }
        }
        logFile.writeln("  [" + li + "] '" + layer.name + "' — " + typeStr);
    }

    // ── Set text layers ──────────────────────────────────────────────────
    // We search ALL comps in the project, not just MAIN_COMP.
    // This handles AE templates where layers live inside a precomp (e.g. Main_BUILD).
    logFile.writeln("--- Setting text ---");
    yosukiSetTextLayer("SERIES_TITLE_TEXT", data.series_title, logFile);
    yosukiSetTextLayer("TAGLINE_TEXT",       data.tagline,      logFile);
    yosukiSetTextLayer("CTA_TEXT",           data.cta,          logFile);

    // ── Relink footage ───────────────────────────────────────────────────
    logFile.writeln("--- Relinking footage ---");
    yosukiRelinkFootage("BG_IMAGE_PLACEHOLDER",      data.bg_image_path,      logFile);
    yosukiRelinkFootage("PRODUCT_IMAGE_PLACEHOLDER", data.product_image_path, logFile);

    // ── Constrain OR manually scale/position product ─────────────────────
    // If use_product_constrain is true, the product is fitted inside the
    // PRODUCT_CONSTRAIN solid (contain-style: fills as large as possible
    // without exceeding the box). Position snaps to the constrain layer too.
    // Otherwise, fall back to the manual product_scale / product_position values.
    if (data.use_product_constrain) {
        logFile.writeln("--- Constraining product to PRODUCT_CONSTRAIN ---");
        // Pass product_scale as an optional manual override.
        // If it's set (e.g. 37), that scale is used directly.
        // If null, the function auto-calculates a contain (fit-inside) scale.
        yosukiConstrainToLayer("PRODUCT_IMAGE_PLACEHOLDER", "PRODUCT_CONSTRAIN", data.product_scale, data.constrain_y_offset, logFile);
    } else {
        if (data.product_scale !== undefined && data.product_scale !== null) {
            logFile.writeln("--- Scaling product ---");
            yosukiSetScale("PRODUCT_IMAGE_PLACEHOLDER", data.product_scale, logFile);
        }
        // product_scale_multiplier: multiply the layer's CURRENT AE scale by this value.
        // e.g. 1.1 = 10% larger than whatever the AE template already has.
        if (data.product_scale_multiplier !== undefined && data.product_scale_multiplier !== null) {
            logFile.writeln("--- Scaling product (multiplier) ---");
            yosukiScaleMultiply("PRODUCT_IMAGE_PLACEHOLDER", data.product_scale_multiplier, logFile);
        }
        if (data.product_position !== undefined && data.product_position !== null) {
            logFile.writeln("--- Positioning product ---");
            yosukiSetPosition("PRODUCT_IMAGE_PLACEHOLDER", data.product_position, logFile);
        }
    }

    // ── Tint product to match background ─────────────────────────────────
    // Applies AE's built-in Tint effect to PRODUCT_IMAGE_PLACEHOLDER so the
    // product blends into the scene's colour palette.
    if (data.bg_tint_color && data.bg_tint_amount !== undefined) {
        logFile.writeln("--- Applying product tint ---");
        yosukiApplyTint("PRODUCT_IMAGE_PLACEHOLDER", data.bg_tint_color, data.bg_tint_amount, logFile);
    }

    logFile.writeln("=== yosukiPopulate done ===");
    logFile.close();

    $.writeln("yosukiPopulate: done.");
}


// ─────────────────────────────────────────────
// TEXT LAYER HELPER
// ─────────────────────────────────────────────

function yosukiSetTextLayer(layerName, newText, logFile) {
    // Search through ALL comps in the project.
    // Handles templates where text layers live inside a precomp (e.g. Main_BUILD)
    // rather than directly in MAIN_COMP.
    for (var c = 1; c <= app.project.numItems; c++) {
        var item = app.project.item(c);
        if (!(item instanceof CompItem)) continue;
        for (var i = 1; i <= item.numLayers; i++) {
            var layer = item.layer(i);
            if (layer.name === layerName) {
                if (layer instanceof TextLayer) {
                    var textDoc = layer.property("Source Text").value;
                    textDoc.text = newText;
                    layer.property("Source Text").setValue(textDoc);
                    logFile.writeln("  TEXT SET: '" + layerName + "' = '" + newText + "' (in comp: " + item.name + ")");
                    return;
                } else {
                    logFile.writeln("  WARNING: '" + layerName + "' found in '" + item.name + "' but not a TextLayer.");
                    return;
                }
            }
        }
    }
    logFile.writeln("  WARNING: text layer '" + layerName + "' not found in any comp.");
}


// ─────────────────────────────────────────────
// TINT HELPER
// Applies AE's built-in Tint effect to the named layer.
// color = [r, g, b] as integers 0-255
// amount = 0-100 (how strongly to tint)
// ─────────────────────────────────────────────

function yosukiApplyTint(layerName, color, amount, logFile) {
    // Find the layer across all comps
    var targetLayer = null;
    for (var c = 1; c <= app.project.numItems; c++) {
        var item = app.project.item(c);
        if (!(item instanceof CompItem)) continue;
        for (var i = 1; i <= item.numLayers; i++) {
            if (item.layer(i).name === layerName) {
                targetLayer = item.layer(i);
                break;
            }
        }
        if (targetLayer) break;
    }

    if (!targetLayer) {
        logFile.writeln("  TINT WARNING: layer '" + layerName + "' not found.");
        return;
    }

    try {
        // Remove any existing Tint effect first to avoid duplicates on re-render
        var effects = targetLayer.Effects;
        for (var e = effects.numProperties; e >= 1; e--) {
            if (effects.property(e).matchName === "ADBE Tint") {
                effects.property(e).remove();
            }
        }

        // Add the Tint effect
        // Tint maps: black areas → Map Black To color, white areas → Map White To color
        // We map black → bg tint color, white → white (preserves highlights)
        var fx = effects.addProperty("ADBE Tint");
        fx.property("Map Black To").setValue([color[0]/255, color[1]/255, color[2]/255]);
        fx.property("Map White To").setValue([1, 1, 1]);
        fx.property("Amount to Tint").setValue(amount);

        logFile.writeln("  TINT SET: '" + layerName + "' rgb(" +
            color[0] + "," + color[1] + "," + color[2] + ") at " + amount + "%");
    } catch (e) {
        logFile.writeln("  TINT ERROR: " + e.toString());
    }
}


// ─────────────────────────────────────────────
// SCALE HELPER
// Sets the scale of the named layer across all comps.
// scale = number 0-100 (percentage)
// ─────────────────────────────────────────────

function yosukiSetScale(layerName, scale, logFile) {
    for (var c = 1; c <= app.project.numItems; c++) {
        var item = app.project.item(c);
        if (!(item instanceof CompItem)) continue;
        for (var i = 1; i <= item.numLayers; i++) {
            var layer = item.layer(i);
            if (layer.name === layerName) {
                try {
                    layer.transform.scale.setValue([scale, scale]);
                    logFile.writeln("  SCALE SET: '" + layerName + "' = " + scale + "% (in comp: " + item.name + ")");
                } catch (e) {
                    logFile.writeln("  SCALE ERROR: " + e.toString());
                }
                return;
            }
        }
    }
    logFile.writeln("  SCALE WARNING: layer '" + layerName + "' not found.");
}


// ─────────────────────────────────────────────
// POSITION HELPER
// Moves the named layer's anchor point to a position.
// position = "center"  → moves to the exact centre of the comp that contains the layer
// position = [x, y]    → moves to specific comp pixel coordinates
// ─────────────────────────────────────────────

function yosukiSetPosition(layerName, position, logFile) {
    for (var c = 1; c <= app.project.numItems; c++) {
        var item = app.project.item(c);
        if (!(item instanceof CompItem)) continue;
        for (var i = 1; i <= item.numLayers; i++) {
            var layer = item.layer(i);
            if (layer.name === layerName) {
                try {
                    var x, y;
                    if (position === "center") {
                        // Use the containing comp's dimensions to find dead centre
                        x = item.width  / 2;
                        y = item.height / 2;
                    } else {
                        x = position[0];
                        y = position[1];
                    }
                    layer.transform.position.setValue([x, y]);
                    logFile.writeln("  POSITION SET: '" + layerName + "' = [" + x + ", " + y + "] (in comp: " + item.name + ")");
                } catch (e) {
                    logFile.writeln("  POSITION ERROR: " + e.toString());
                }
                return;
            }
        }
    }
    logFile.writeln("  POSITION WARNING: layer '" + layerName + "' not found.");
}


// ─────────────────────────────────────────────
// FOOTAGE RELINKING HELPER
// ─────────────────────────────────────────────

function yosukiRelinkFootage(layerName, newFilePath, logFile) {
    logFile.writeln("  Relinking '" + layerName + "' to: " + newFilePath);

    // Check file exists
    var newFile = new File(newFilePath);
    logFile.writeln("    file exists: " + newFile.exists);
    if (!newFile.exists) {
        logFile.writeln("    ERROR: file not found on disk!");
        return;
    }

    // Find the layer — search ALL comps in the project
    var targetLayer = null;
    for (var c = 1; c <= app.project.numItems; c++) {
        var item = app.project.item(c);
        if (!(item instanceof CompItem)) continue;
        for (var i = 1; i <= item.numLayers; i++) {
            if (item.layer(i).name === layerName) {
                targetLayer = item.layer(i);
                logFile.writeln("    found in comp: " + item.name);
                break;
            }
        }
        if (targetLayer) break;
    }

    if (!targetLayer) {
        logFile.writeln("    ERROR: layer not found in any comp.");
        return;
    }

    if (!(targetLayer instanceof AVLayer)) {
        logFile.writeln("    ERROR: layer is not an AVLayer.");
        return;
    }

    var currentSource = targetLayer.source;
    logFile.writeln("    current source: " + (currentSource ? currentSource.name : "null"));
    logFile.writeln("    is FootageItem: " + (currentSource instanceof FootageItem));

    // Strategy A: replace() on the existing FootageItem
    if (currentSource instanceof FootageItem) {
        try {
            currentSource.replace(newFile);
            logFile.writeln("    Strategy A (replace): OK — new file: " +
                            (currentSource.file ? currentSource.file.name : "null"));
            return;
        } catch (e) {
            logFile.writeln("    Strategy A FAILED: " + e.toString());
        }
    }

    // Strategy B: importFile() + replaceSource()
    try {
        var importOpts = new ImportOptions(newFile);
        importOpts.sequence = false;
        var newFootageItem = app.project.importFile(importOpts);
        if (!newFootageItem) {
            logFile.writeln("    Strategy B: importFile returned null.");
            return;
        }
        targetLayer.replaceSource(newFootageItem, true);
        logFile.writeln("    Strategy B (importFile+replaceSource): OK");
    } catch (e) {
        logFile.writeln("    Strategy B FAILED: " + e.toString());
    }
}


// ─────────────────────────────────────────────
// CONSTRAIN HELPER
// Fits productLayerName inside constrainLayerName using "contain" scaling:
// scales the product as large as possible without exceeding the constraint box,
// preserving the product's aspect ratio. Also snaps the product's position
// to match the constraint layer's position.
// ─────────────────────────────────────────────

function yosukiConstrainToLayer(productLayerName, constrainLayerName, manualScale, yOffset, logFile) {

    // ── Find both layers across all comps ───────────────────────────
    var productLayer   = null;
    var constrainLayer = null;

    for (var c = 1; c <= app.project.numItems; c++) {
        var item = app.project.item(c);
        if (!(item instanceof CompItem)) continue;
        for (var i = 1; i <= item.numLayers; i++) {
            var layer = item.layer(i);
            if (layer.name === productLayerName  && !productLayer)   { productLayer   = layer; }
            if (layer.name === constrainLayerName && !constrainLayer) { constrainLayer = layer; }
        }
        if (productLayer && constrainLayer) break;
    }

    if (!productLayer) {
        logFile.writeln("  CONSTRAIN ERROR: product layer '"   + productLayerName   + "' not found.");
        return;
    }
    if (!constrainLayer) {
        logFile.writeln("  CONSTRAIN ERROR: constrain layer '" + constrainLayerName + "' not found.");
        return;
    }

    // ── Get the constraint box's effective pixel size ────────────────
    // The solid may have a scale transform applied to it, so multiply
    // source dimensions by that scale to get the real on-screen size.
    var constrainScale = constrainLayer.transform.scale.value;  // [sx%, sy%]
    var constrainW = constrainLayer.source.width  * (constrainScale[0] / 100);
    var constrainH = constrainLayer.source.height * (constrainScale[1] / 100);

    // ── Get the product image's source pixel dimensions ──────────────
    var productW = productLayer.source.width;
    var productH = productLayer.source.height;

    // ── Determine scale ──────────────────────────────────────────────
    // If a manual scale was passed in (e.g. 37 from the data JSON), use it.
    // Otherwise auto-calculate: contain = Math.min so the product never
    // exceeds the box on either dimension.
    var fitScale;
    if (manualScale !== null && manualScale !== undefined) {
        fitScale = manualScale;
        logFile.writeln("  Using manual scale: " + fitScale + "%");
    } else {
        var scaleX = (constrainW / productW) * 100;
        var scaleY = (constrainH / productH) * 100;
        fitScale = Math.min(scaleX, scaleY);  // contain: fit inside the box
        logFile.writeln("  Auto-calculated scale (contain): " + fitScale.toFixed(1) + "%");
    }

    // ── Apply scale and snap position to the constraint layer ────────
    // yOffset shifts the final Y position (negative = up, positive = down).
    productLayer.transform.scale.setValue([fitScale, fitScale]);
    var constrainPos = constrainLayer.transform.position.value;
    var offsetY = (yOffset !== null && yOffset !== undefined) ? yOffset : 0;
    var finalPos = [constrainPos[0], constrainPos[1] + offsetY];
    productLayer.transform.position.setValue(finalPos);

    logFile.writeln("  CONSTRAIN SET:");
    logFile.writeln("    box:     " + constrainW.toFixed(0) + " x " + constrainH.toFixed(0) + " px");
    logFile.writeln("    product: " + productW + " x " + productH + " px (source)");
    logFile.writeln("    scale:   " + fitScale.toFixed(1) + "%");
    logFile.writeln("    y_offset: " + offsetY + " px");
    logFile.writeln("    pos:     [" + finalPos[0] + ", " + finalPos[1] + "]");
}

// ─────────────────────────────────────────────────────
// yosukiScaleMultiply — multiply a layer's current AE
// scale by a factor (e.g. 1.1 = 10% bigger).
// ─────────────────────────────────────────────────────
function yosukiScaleMultiply(layerName, multiplier, logFile) {
    var targetLayer = null;
    for (var c = 1; c <= app.project.numItems; c++) {
        var item = app.project.item(c);
        if (!(item instanceof CompItem)) continue;
        for (var i = 1; i <= item.numLayers; i++) {
            if (item.layer(i).name === layerName) {
                targetLayer = item.layer(i);
                break;
            }
        }
        if (targetLayer) break;
    }
    if (!targetLayer) {
        logFile.writeln("  SCALE MULTIPLY ERROR: layer '" + layerName + "' not found.");
        return;
    }
    var currentScale = targetLayer.transform.scale.value[0];
    var newScale     = currentScale * multiplier;
    targetLayer.transform.scale.setValue([newScale, newScale]);
    logFile.writeln("  SCALE MULTIPLY: " + currentScale.toFixed(1) + "% x " + multiplier + " = " + newScale.toFixed(1) + "%");
}
