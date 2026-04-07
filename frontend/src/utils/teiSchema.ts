/**
 * TEI P5 schema parser for CodeMirror 5 hintOptions.schemaInfo format.
 *
 * Rewritten as an ES module — no jQuery dependency.
 * Uses fetch + DOMParser (available in all modern browsers).
 *
 * Original logic: cm-tei-schema.js by Alfredo Cosco.
 * Ported to TypeScript for Aracne2.
 */

// ── Types ─────────────────────────────────────────────────────────────────────

/** A node in the intermediate JSON representation of the schema XML. */
interface SchemaNode {
  attrs?: Record<string, string[]>;
  children?: string[] | string;
  _?: string;
  [key: string]: unknown;
}

/** CM5 hintOptions.schemaInfo format consumed by @codemirror/xml-hint. */
export type CM5Schema = Record<string, unknown>;

// ── XML → intermediate JSON ───────────────────────────────────────────────────

function normalizeText(value: string): string {
  return value ?? '';
}

function xmlElementToNode(el: Element): SchemaNode {
  const result: SchemaNode = {};
  const attrs: Record<string, string[]> = {};
  result['attrs'] = attrs;

  // Collect element attributes
  for (let i = 0; i < el.attributes.length; i++) {
    const item = el.attributes.item(i)!;
    const parts = item.value.split(',');
    attrs[item.nodeName] = parts.length > 1 ? parts : [item.value];
  }

  // Leaf node: capture text content
  if (el.childElementCount === 0) {
    result['_'] = normalizeText(el.textContent ?? '');
  }

  // Recurse into child elements
  for (let i = 0; i < el.childNodes.length; i++) {
    const node = el.childNodes[i] as Element;
    if (node.nodeType !== 1) continue; // skip text/comment nodes

    let child: SchemaNode | string;

    if (node.attributes.length === 0 && node.childElementCount === 0) {
      child = normalizeText(node.textContent ?? '');
    } else {
      child = xmlElementToNode(node);
    }

    const name = node.nodeName;

    if (Object.prototype.hasOwnProperty.call(result, name)) {
      // Promote to array on repeated elements
      const existing = result[name];
      if (!Array.isArray(existing)) {
        result[name] = [existing as SchemaNode];
      }
      (result[name] as SchemaNode[]).push(child as SchemaNode);
    } else if (name === 'children' && typeof child === 'string') {
      // <children> text is a comma-separated list of tag names.
      // CM5 xml-hint expects result.children to be string[], not a single string.
      result[name] = child.split(',').map(s => s.trim()).filter(Boolean);
    } else {
      result[name] = child;
    }
  }

  return result;
}

// ── Document → CM5 schema ─────────────────────────────────────────────────────

function documentToSchema(doc: Document): CM5Schema {
  // The XML root must be <cm_tei_schema>.
  // Replicates the original jQuery $.ajax response structure where the
  // response is a Document and root['#document']['cm_tei_schema'] is used.
  const schemaEl = doc.documentElement;

  // Build the intermediate node from the root element's children
  const inner = xmlElementToNode(schemaEl);

  // Extract !top (the allowed top-level elements list)
  const topValue = inner['top'];
  delete inner['top'];
  // Remove the attrs wrapper from the root — not needed at schema level
  delete inner['attrs'];

  return Object.assign({ '!top': [topValue] }, inner) as CM5Schema;
}

// ── Public API ────────────────────────────────────────────────────────────────

/**
 * Load and parse a TEI P5 XML schema into the format expected by
 * CodeMirror 5's xml-hint addon (hintOptions.schemaInfo).
 *
 * @param source  Either a URL string (fetched) or raw XML text (parsed directly),
 *                depending on the *mode* parameter.
 * @param mode    'url'  — fetch the URL and parse the response (default).
 *               'text' — parse *source* directly as XML text (used when the
 *                         backend serves the CM5 file content via API).
 */
export async function loadTeiSchema(source: string, mode: 'url' | 'text' = 'url'): Promise<CM5Schema> {
  let text: string;
  if (mode === 'text') {
    text = source;
  } else {
    const response = await fetch(source);
    if (!response.ok) {
      throw new Error(`Failed to load TEI schema from ${source}: HTTP ${response.status}`);
    }
    text = await response.text();
  }
  const parser = new DOMParser();
  const doc = parser.parseFromString(text, 'application/xml');
  const parseError = doc.querySelector('parsererror');
  if (parseError) {
    throw new Error(`Invalid XML schema: ${parseError.textContent}`);
  }
  return documentToSchema(doc);
}
