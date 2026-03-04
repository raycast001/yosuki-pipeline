/**
 * populate_template.jsx — After Effects ExtendScript
 * ====================================================
 * Reads a data JSON file and populates the AE project:
 *   - Sets text on SERIES_TITLE_TEXT, TAGLINE_TEXT, CTA_TEXT layers
 *   - Relinks BG_IMAGE_PLACEHOLDER and PRODUCT_IMAGE_PLACEHOLDER footage
 *
 * Writes a jsx_debug.log file next to the .aep so we can see what happened
 * even in headless aerender mode (where $.writeln is invisible).
 */


// ─────────────────────────────────────────────
// FILE-BASED LOGGING (visible in headless mode)
// ─────────────────────────────────────────────

var LOG_FILE = null;

/**
 * initLog()
 * Opens a log file next to the project for writing.
 * Called once at the start of main().
 */
function initLog(projectFolder) {
    LOG_FILE = new File(projectFolder + "/jsx_debug.log");
    LOG_FILE.encoding = "UTF-8";
    LOG_FILE.open("w");  // overwrite any previous log
    logLine("=== populate_template.jsx started ===");
}

/**
 * logLine(msg)
 * Writes a line to the log file AND to the ESTK console.
 */
function logLine(msg) {
    $.writeln(msg);
    if (LOG_FILE && LOG_FILE.isOpen) {
        LOG_FILE.writeln(msg);
    }
}

function closeLog() {
    logLine("=== populate_template.jsx finished ===");
    if (LOG_FILE && LOG_FILE.isOpen) {
        LOG_FILE.close();
    }
}


// ─────────────────────────────────────────────
// STEP 1 — FIND THE DATA JSON FILE
// ─────────────────────────────────────────────

function findDataJson() {
    var projectFile = app.project.file;
    if (!projectFile) {
        logLine("ERROR: No project file found.");
        return null;
    }

    logLine("Project file: " + projectFile.fsName);

    var projectName = projectFile.name.replace(/\.aep$/i, "");
    var dataFileName = projectName + "_data.json";
    var dataFile = new File(projectFile.parent.fsName + "/" + dataFileName);

    logLine("Looking for data file: " + dataFile.fsName);
    logLine("Data file exists: " + dataFile.exists);

    if (!dataFile.exists) {
        logLine("ERROR: Data file not found.");
        return null;
    }

    return dataFile;
}


// ─────────────────────────────────────────────
// STEP 2 — READ AND PARSE THE JSON
// ─────────────────────────────────────────────

function readDataJson(file) {
    file.encoding = "UTF-8";
    if (!file.open("r")) {
        logLine("ERROR: Cannot open data file.");
        return null;
    }

    var content = file.read();
    file.close();

    if (!content || content.length === 0) {
        logLine("ERROR: Data file is empty.");
        return null;
    }

    var data;
    try {
        data = eval("(" + content + ")");
    } catch (e) {
        logLine("ERROR: Failed to parse JSON: " + e.toString());
        return null;
    }

    return data;
}


// ─────────────────────────────────────────────
// STEP 3 — FIND THE MAIN COMP
// ─────────────────────────────────────────────

function findMainComp(compName) {
    logLine("Searching for comp: '" + compName + "'");
    logLine("Total project items: " + app.project.numItems);

    for (var i = 1; i <= app.project.numItems; i++) {
        var item = app.project.item(i);
        logLine("  Item " + i + ": '" + item.name + "' type=" + item.toString());
        if (item instanceof CompItem && item.name === compName) {
            logLine("  FOUND: " + compName);
            return item;
        }
    }

    logLine("ERROR: Comp '" + compName + "' not found.");
    return null;
}


// ─────────────────────────────────────────────
// STEP 4 — DUMP ALL LAYERS (for diagnosis)
// ─────────────────────────────────────────────

/**
 * dumpLayers(comp)
 * Logs every layer in the comp with its name and type.
 * This tells us EXACTLY what layers exist and what type they are.
 */
function dumpLayers(comp) {
    logLine("--- Layers in '" + comp.name + "' (" + comp.numLayers + " total) ---");
    for (var i = 1; i <= comp.numLayers; i++) {
        var layer = comp.layer(i);
        var layerType = "unknown";

        if (layer instanceof TextLayer)       { layerType = "TEXT"; }
        else if (layer instanceof ShapeLayer) { layerType = "SHAPE"; }
        else if (layer instanceof LightLayer) { layerType = "LIGHT"; }
        else if (layer instanceof CameraLayer){ layerType = "CAMERA"; }
        else if (layer instanceof AVLayer) {
            // AVLayer is the base class for footage, solid, and precomp layers
            if (layer.source instanceof CompItem) {
                layerType = "PRECOMP (source='" + layer.source.name + "')";
            } else if (layer.source instanceof FootageItem) {
                layerType = "FOOTAGE (source='" + layer.source.name + "', file=" + (layer.source.file ? layer.source.file.fsName : "no file") + ")";
            } else {
                layerType = "AVLAYER (solid or other)";
            }
        }

        logLine("  [" + i + "] '" + layer.name + "' — " + layerType);
    }
    logLine("--- End layer list ---");
}


// ─────────────────────────────────────────────
// STEP 5 — SET TEXT LAYERS
// ─────────────────────────────────────────────

function setTextLayer(comp, layerName, newText) {
    for (var i = 1; i <= comp.numLayers; i++) {
        var layer = comp.layer(i);
        if (layer.name === layerName) {
            if (layer instanceof TextLayer) {
                var textDoc = layer.property("Source Text").value;
                textDoc.text = newText;
                layer.property("Source Text").setValue(textDoc);
                logLine("  Text set: '" + layerName + "' = '" + newText + "'");
                return true;
            } else {
                logLine("  WARNING: '" + layerName + "' found but is not a TextLayer.");
                return false;
            }
        }
    }
    logLine("  WARNING: Text layer '" + layerName + "' not found.");
    return false;
}


// ─────────────────────────────────────────────
// STEP 6 — RELINK FOOTAGE
// ─────────────────────────────────────────────

/**
 * relinkFootage(comp, layerName, newFilePath)
 *
 * Strategy: find the layer, get its EXISTING source FootageItem,
 * and call .replace() on that item to change the file it points to.
 *
 * This modifies the footage item that's already wired up in the composition,
 * rather than creating a new item and re-wiring. It's the most direct approach.
 */
function relinkFootage(comp, layerName, newFilePath) {
    logLine("  Relinking '" + layerName + "' to: " + newFilePath);

    // 1. Check the file exists on disk
    var newFile = new File(newFilePath);
    logLine("    File exists on disk: " + newFile.exists);

    if (!newFile.exists) {
        logLine("    ERROR: File not found on disk!");
        return false;
    }

    // 2. Find the layer
    var targetLayer = null;
    for (var i = 1; i <= comp.numLayers; i++) {
        if (comp.layer(i).name === layerName) {
            targetLayer = comp.layer(i);
            break;
        }
    }

    if (!targetLayer) {
        logLine("    ERROR: Layer '" + layerName + "' not found in comp '" + comp.name + "'.");
        return false;
    }

    logLine("    Layer found. Is AVLayer: " + (targetLayer instanceof AVLayer));

    // 3. Check the layer has a source
    if (!(targetLayer instanceof AVLayer)) {
        logLine("    ERROR: Layer is not an AVLayer — cannot relink footage.");
        return false;
    }

    var currentSource = targetLayer.source;
    logLine("    Current source: " + (currentSource ? currentSource.name : "null"));
    logLine("    Source is FootageItem: " + (currentSource instanceof FootageItem));
    logLine("    Source is CompItem: " + (currentSource instanceof CompItem));

    // 4. Try strategy A: replace() on the existing FootageItem
    //    This changes the file the existing footage item points to.
    //    All layers using this footage item update automatically.
    if (currentSource instanceof FootageItem) {
        try {
            logLine("    Strategy A: calling currentSource.replace(newFile)...");
            currentSource.replace(newFile);
            logLine("    Strategy A: replace() called. New file: " + (currentSource.file ? currentSource.file.fsName : "null"));
            return true;
        } catch (e) {
            logLine("    Strategy A FAILED: " + e.toString());
        }
    }

    // 5. Try strategy B: importFile() + replaceSource()
    //    Import as a new footage item, then point the layer at it.
    try {
        logLine("    Strategy B: importFile() + replaceSource()...");
        var importOptions = new ImportOptions(newFile);
        importOptions.sequence = false;
        var newFootageItem = app.project.importFile(importOptions);
        logLine("    Imported footage item: " + (newFootageItem ? newFootageItem.name : "null"));

        if (!newFootageItem) {
            logLine("    Strategy B FAILED: importFile returned null.");
            return false;
        }

        targetLayer.replaceSource(newFootageItem, true);
        logLine("    Strategy B: replaceSource() called OK.");
        return true;
    } catch (e) {
        logLine("    Strategy B FAILED: " + e.toString());
        return false;
    }
}


// ─────────────────────────────────────────────
// MAIN
// ─────────────────────────────────────────────

function main() {
    app.beginUndoGroup("Populate Template");

    try {
        var projectFile = app.project.file;
        var projectFolder = projectFile ? projectFile.parent.fsName : Folder.temp.fsName;
        initLog(projectFolder);

        // ── Find + read the data file ──────────────────────────────
        var dataFile = findDataJson();
        if (!dataFile) { closeLog(); return; }

        var data = readDataJson(dataFile);
        if (!data) { closeLog(); return; }

        logLine("Variant: " + data.variant_id);
        logLine("bg_image_path: " + data.bg_image_path);
        logLine("product_image_path: " + data.product_image_path);

        // ── Find the main comp ──────────────────────────────────────
        var compName = data.comp_name || "MAIN_COMP";
        var comp = findMainComp(compName);
        if (!comp) { closeLog(); return; }

        // ── Dump all layers so we can see what's there ──────────────
        dumpLayers(comp);

        // ── Set text layers ─────────────────────────────────────────
        logLine("Setting text layers...");
        setTextLayer(comp, "SERIES_TITLE_TEXT", data.series_title);
        setTextLayer(comp, "TAGLINE_TEXT",       data.tagline);
        setTextLayer(comp, "CTA_TEXT",           data.cta);

        // ── Relink footage layers ───────────────────────────────────
        logLine("Relinking footage...");
        var bgResult      = relinkFootage(comp, "BG_IMAGE_PLACEHOLDER",      data.bg_image_path);
        var productResult = relinkFootage(comp, "PRODUCT_IMAGE_PLACEHOLDER", data.product_image_path);

        logLine("Results:");
        logLine("  BG_IMAGE_PLACEHOLDER:      " + (bgResult      ? "OK" : "FAILED"));
        logLine("  PRODUCT_IMAGE_PLACEHOLDER: " + (productResult ? "OK" : "FAILED"));

    } catch (e) {
        logLine("FATAL ERROR: " + e.toString());
        alert("populate_template.jsx error:\n" + e.toString());
    } finally {
        closeLog();
        app.endUndoGroup();
    }
}

main();
