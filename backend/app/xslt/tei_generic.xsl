<?xml version="1.0" encoding="UTF-8"?>
<!--
  tei_generic.xsl — Generic TEI P5 to HTML (XSLT 1.0, lxml-compatible)

  Designed for manuscript and epistolary transcriptions.  Handles the most
  common TEI elements used in critical editions; unknown elements are rendered
  as their text content so nothing is silently dropped.

  To customise rendering for a specific collection, upload a per-schema XSLT
  file via Settings → Schemas once the Designer-role feature is implemented
  (see docs/DEFERRED.md item 6).
-->
<xsl:stylesheet version="1.0"
  xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
  xmlns:tei="http://www.tei-c.org/ns/1.0"
  exclude-result-prefixes="tei">

  <xsl:output method="html" encoding="UTF-8" indent="yes" doctype-public="" doctype-system=""/>

  <!-- ═══════════════════════════════════════════════════════════════════════ -->
  <!-- Root                                                                    -->
  <!-- ═══════════════════════════════════════════════════════════════════════ -->

  <xsl:template match="/tei:TEI">
    <html lang="it">
      <head>
        <meta charset="UTF-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1"/>
        <title>
          <xsl:value-of select="tei:teiHeader/tei:fileDesc/tei:titleStmt/tei:title[1]"/>
        </title>
        <style>
          *, *::before, *::after { box-sizing: border-box; }
          body {
            font-family: Georgia, 'Times New Roman', serif;
            font-size: 1rem;
            line-height: 1.85;
            color: #1a1a1a;
            max-width: 780px;
            margin: 2rem auto;
            padding: 0 1.25rem;
            background: #fff;
          }
          /* ── Header ─────────────────────────────────────────────────────── */
          .tei-header {
            border-bottom: 2px solid #e2e2e2;
            margin-bottom: 2.5rem;
            padding-bottom: 1.25rem;
          }
          h1.tei-title {
            font-size: 1.5rem;
            font-weight: bold;
            margin: 0 0 0.3rem;
          }
          p.tei-author  { color: #555; margin: 0 0 0.25rem; font-style: italic; }
          p.tei-pub     { color: #777; font-size: 0.85rem; margin: 0; }
          /* ── Body / Divisions ────────────────────────────────────────────── */
          section.tei-div { margin: 0; }
          h2.tei-head { font-size: 1.15rem; margin: 1.75rem 0 0.6rem; font-style: italic; }
          h3.tei-head { font-size: 1rem;    margin: 1.4rem 0 0.5rem;  font-style: italic; }
          h4.tei-head { font-size: 0.9rem;  margin: 1.2rem 0 0.4rem;  font-style: italic; }
          /* ── Paragraphs ──────────────────────────────────────────────────── */
          p.tei-p      { margin: 0.9em 0; text-align: justify; hyphens: auto; }
          p.tei-p + p.tei-p { text-indent: 1.4em; }
          /* ── Page / column / line breaks ─────────────────────────────────── */
          span.tei-pb {
            display: block; text-align: center;
            font-size: 0.75rem; color: #aaa;
            margin: 0.8rem 0 0.4rem;
            letter-spacing: 0.05em;
          }
          figure.tei-pb-facsimile {
            display: block;
            margin: 2rem auto;
            text-align: center;
            border: 1px solid #e5e7eb;
            border-radius: 3px;
            padding: 0.5rem;
            background: #fafafa;
          }
          figure.tei-pb-facsimile img {
            max-width: 100%;
            height: auto;
            display: block;
            margin: 0 auto;
          }
          figcaption.tei-pb-label {
            margin-top: 0.3rem;
            font-size: 0.72rem;
            color: #9ca3af;
            font-family: monospace;
            letter-spacing: 0.04em;
          }
          span.tei-cb { color: #bbb; margin: 0 0.2em; }
          /* ── Named entities ──────────────────────────────────────────────── */
          span.tei-persname  { color: #9b3000; border-bottom: 1px dotted #9b3000; }
          span.tei-placename { color: #005520; border-bottom: 1px dotted #005520; }
          span.tei-orgname   { color: #003580; border-bottom: 1px dotted #003580; }
          span.tei-date      { color: #44447a; }
          /* ── Textual criticism ───────────────────────────────────────────── */
          span.tei-gap      { color: #aaa; font-style: italic; }
          span.tei-supplied { color: #666; }
          span.tei-unclear  { color: #999; border-bottom: 1px dotted #999; }
          del.tei-del       { color: #bbb; text-decoration: line-through; }
          span.tei-add      { color: #447; font-size: 0.9em; vertical-align: super; }
          span.tei-normalized { /* choice/reg — invisible by default */ }
          /* ── Abbreviations / expansion ───────────────────────────────────── */
          abbr.tei-abbr {
            text-decoration: underline dotted #999;
            cursor: help;
          }
          /* ── References ─────────────────────────────────────────────────── */
          a.tei-ref { color: inherit; text-decoration: underline; }
          cite.tei-title-inline { font-style: italic; }
          /* ── Footnote markers ────────────────────────────────────────────── */
          span.tei-note-marker {
            display: inline-block; vertical-align: super;
            font-size: 0.7rem; color: #888; cursor: pointer;
            margin: 0 0.1em; background: #f5f5f5;
            border: 1px solid #ddd; border-radius: 2px; padding: 0 0.2em;
          }
          aside.tei-notes {
            margin-top: 3rem; border-top: 1px solid #e2e2e2;
            padding-top: 1rem; font-size: 0.85rem; color: #555;
          }
          aside.tei-notes p { margin: 0.4rem 0; }
          /* ── Quote / said ────────────────────────────────────────────────── */
          q.tei-q { quotes: "\201C" "\201D" "\2018" "\2019"; }
          blockquote.tei-quote { margin: 1rem 2rem; font-style: italic; }
          /* ── Figures / images ────────────────────────────────────────────── */
          figure.tei-figure {
            margin: 1.5rem auto;
            max-width: 100%;
            text-align: center;
          }
          figure.tei-figure img {
            max-width: 100%;
            height: auto;
            display: block;
            margin: 0 auto;
            border: 1px solid #e2e2e2;
            border-radius: 2px;
          }
          figcaption.tei-figdesc {
            margin-top: 0.4rem;
            font-size: 0.82rem;
            color: #666;
            font-style: italic;
          }
          img.tei-graphic {
            max-width: 100%;
            height: auto;
            display: block;
            margin: 1rem auto;
          }
        </style>
      </head>
      <body>
        <xsl:apply-templates select="tei:teiHeader"/>
        <xsl:apply-templates select="tei:text"/>
      </body>
    </html>
  </xsl:template>

  <!-- ═══════════════════════════════════════════════════════════════════════ -->
  <!-- teiHeader                                                               -->
  <!-- ═══════════════════════════════════════════════════════════════════════ -->

  <xsl:template match="tei:teiHeader">
    <header class="tei-header">
      <xsl:apply-templates select="tei:fileDesc/tei:titleStmt"/>
      <xsl:apply-templates select="tei:fileDesc/tei:publicationStmt"/>
    </header>
  </xsl:template>

  <xsl:template match="tei:titleStmt">
    <h1 class="tei-title">
      <xsl:apply-templates select="tei:title[1]"/>
    </h1>
    <xsl:for-each select="tei:author">
      <p class="tei-author"><xsl:apply-templates/></p>
    </xsl:for-each>
    <xsl:for-each select="tei:editor">
      <p class="tei-author">Ed. <xsl:apply-templates/></p>
    </xsl:for-each>
  </xsl:template>

  <xsl:template match="tei:publicationStmt">
    <xsl:if test="tei:publisher or tei:date or tei:pubPlace">
      <p class="tei-pub">
        <xsl:if test="tei:publisher">
          <xsl:value-of select="tei:publisher"/>
          <xsl:if test="tei:pubPlace or tei:date">, </xsl:if>
        </xsl:if>
        <xsl:if test="tei:pubPlace">
          <xsl:value-of select="tei:pubPlace"/>
          <xsl:if test="tei:date">, </xsl:if>
        </xsl:if>
        <xsl:if test="tei:date">
          <xsl:value-of select="tei:date"/>
        </xsl:if>
      </p>
    </xsl:if>
  </xsl:template>

  <!-- Suppress encoding description and revision history from output -->
  <xsl:template match="tei:encodingDesc | tei:revisionDesc | tei:profileDesc"/>

  <!-- ═══════════════════════════════════════════════════════════════════════ -->
  <!-- text / body / front / back                                              -->
  <!-- ═══════════════════════════════════════════════════════════════════════ -->

  <xsl:template match="tei:text">
    <main class="tei-text">
      <xsl:apply-templates select="tei:front"/>
      <xsl:apply-templates select="tei:body"/>
      <xsl:apply-templates select="tei:back"/>
    </main>
    <!-- Collect all notes at the bottom -->
    <xsl:if test="//tei:note[normalize-space(.) != '']">
      <aside class="tei-notes">
        <xsl:for-each select="//tei:note[normalize-space(.) != '']">
          <p>
            <xsl:value-of select="position()"/>. <xsl:apply-templates/>
          </p>
        </xsl:for-each>
      </aside>
    </xsl:if>
  </xsl:template>

  <xsl:template match="tei:body">
    <div class="tei-body"><xsl:apply-templates/></div>
  </xsl:template>

  <xsl:template match="tei:front">
    <div class="tei-front"><xsl:apply-templates/></div>
  </xsl:template>

  <xsl:template match="tei:back">
    <div class="tei-back"><xsl:apply-templates/></div>
  </xsl:template>

  <!-- ═══════════════════════════════════════════════════════════════════════ -->
  <!-- Divisions                                                               -->
  <!-- ═══════════════════════════════════════════════════════════════════════ -->

  <xsl:template match="tei:div">
    <section>
      <xsl:attribute name="class">
        <xsl:choose>
          <xsl:when test="@type">tei-div tei-div-<xsl:value-of select="@type"/></xsl:when>
          <xsl:otherwise>tei-div</xsl:otherwise>
        </xsl:choose>
      </xsl:attribute>
      <xsl:apply-templates/>
    </section>
  </xsl:template>

  <xsl:template match="tei:head">
    <xsl:choose>
      <xsl:when test="count(ancestor::tei:div) &gt; 2">
        <h4 class="tei-head"><xsl:apply-templates/></h4>
      </xsl:when>
      <xsl:when test="count(ancestor::tei:div) = 2">
        <h3 class="tei-head"><xsl:apply-templates/></h3>
      </xsl:when>
      <xsl:otherwise>
        <h2 class="tei-head"><xsl:apply-templates/></h2>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:template>

  <!-- ═══════════════════════════════════════════════════════════════════════ -->
  <!-- Block-level text elements                                               -->
  <!-- ═══════════════════════════════════════════════════════════════════════ -->

  <xsl:template match="tei:p">
    <p class="tei-p"><xsl:apply-templates/></p>
  </xsl:template>

  <xsl:template match="tei:l">
    <span class="tei-l"><xsl:apply-templates/><br/></span>
  </xsl:template>

  <xsl:template match="tei:lg">
    <div class="tei-lg"><xsl:apply-templates/></div>
  </xsl:template>

  <xsl:template match="tei:quote | tei:cit/tei:quote">
    <blockquote class="tei-quote"><xsl:apply-templates/></blockquote>
  </xsl:template>

  <xsl:template match="tei:said">
    <q class="tei-q"><xsl:apply-templates/></q>
  </xsl:template>

  <xsl:template match="tei:list">
    <ul class="tei-list"><xsl:apply-templates/></ul>
  </xsl:template>

  <xsl:template match="tei:item">
    <li class="tei-item"><xsl:apply-templates/></li>
  </xsl:template>

  <!-- ═══════════════════════════════════════════════════════════════════════ -->
  <!-- Breaks                                                                  -->
  <!-- ═══════════════════════════════════════════════════════════════════════ -->

  <xsl:template match="tei:lb">
    <br/>
  </xsl:template>

  <xsl:template match="tei:cb">
    <span class="tei-cb">&#x7c;</span>
  </xsl:template>

  <xsl:template match="tei:pb">
    <xsl:choose>
      <!-- @facs="#id" — look up the surface in the facsimile block and show its image -->
      <xsl:when test="@facs and starts-with(@facs, '#')">
        <xsl:variable name="surf-id" select="substring-after(@facs, '#')"/>
        <xsl:variable name="img-url"
          select="//tei:surface[@xml:id = $surf-id]/tei:graphic/@url"/>
        <figure class="tei-pb-facsimile">
          <xsl:if test="$img-url != ''">
            <img src="{$img-url}" alt="Facsimile {$surf-id}" class="tei-pb-img"/>
          </xsl:if>
          <figcaption class="tei-pb-label">
            <xsl:choose>
              <xsl:when test="@n">p. <xsl:value-of select="@n"/></xsl:when>
              <xsl:otherwise>#<xsl:value-of select="$surf-id"/></xsl:otherwise>
            </xsl:choose>
          </figcaption>
        </figure>
      </xsl:when>
      <!-- @n only — show page number inline -->
      <xsl:when test="@n">
        <span class="tei-pb">[p. <xsl:value-of select="@n"/>]</span>
      </xsl:when>
      <!-- bare <pb/> — horizontal rule marker -->
      <xsl:otherwise>
        <span class="tei-pb">[&#x2015;]</span>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:template>

  <!-- ═══════════════════════════════════════════════════════════════════════ -->
  <!-- Figures and images                                                      -->
  <!-- ═══════════════════════════════════════════════════════════════════════ -->

  <!--
    <figure>: block container.  Children are processed in order so both
    <graphic> and <figDesc> (caption) are handled by their own templates.
  -->
  <xsl:template match="tei:figure">
    <figure class="tei-figure">
      <xsl:apply-templates/>
    </figure>
  </xsl:template>

  <!--
    <graphic url="…"/>: render as <img>.
    The url attribute may be an API path (/api/v1/…) or a relative path.
    An empty alt is set so screen readers treat it as decorative when no
    desc attribute is present; when @desc is present it becomes the alt text.
  -->
  <xsl:template match="tei:graphic">
    <xsl:variable name="alt">
      <xsl:choose>
        <xsl:when test="@desc"><xsl:value-of select="@desc"/></xsl:when>
        <xsl:otherwise></xsl:otherwise>
      </xsl:choose>
    </xsl:variable>
    <xsl:choose>
      <xsl:when test="parent::tei:figure">
        <!-- Inside <figure>: no extra wrapper -->
        <img class="tei-graphic" src="{@url}" alt="{$alt}"/>
      </xsl:when>
      <xsl:otherwise>
        <!-- Standalone <graphic> outside <figure> -->
        <img class="tei-graphic" src="{@url}" alt="{$alt}"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:template>

  <!-- <figDesc>: caption text rendered as <figcaption> -->
  <xsl:template match="tei:figDesc">
    <figcaption class="tei-figdesc"><xsl:apply-templates/></figcaption>
  </xsl:template>

  <!--
    <facsimile> and its children (<surface>, <zone>) live between
    <teiHeader> and <text>.  The root template does not select them, but
    an explicit suppress is added here as defensive programming so they
    are never accidentally rendered if apply-templates is broadened.
  -->
  <xsl:template match="tei:facsimile | tei:surface | tei:zone"/>

  <!-- ═══════════════════════════════════════════════════════════════════════ -->
  <!-- Highlighting / formatting                                               -->
  <!-- ═══════════════════════════════════════════════════════════════════════ -->

  <xsl:template match="tei:hi[@rend='italic' or @rend='i' or @rend='italics']">
    <em><xsl:apply-templates/></em>
  </xsl:template>

  <xsl:template match="tei:hi[@rend='bold' or @rend='b']">
    <strong><xsl:apply-templates/></strong>
  </xsl:template>

  <xsl:template match="tei:hi[@rend='underline' or @rend='u']">
    <u><xsl:apply-templates/></u>
  </xsl:template>

  <xsl:template match="tei:hi[@rend='superscript' or @rend='sup']">
    <sup><xsl:apply-templates/></sup>
  </xsl:template>

  <xsl:template match="tei:hi[@rend='subscript' or @rend='sub']">
    <sub><xsl:apply-templates/></sub>
  </xsl:template>

  <xsl:template match="tei:hi[@rend='small-caps' or @rend='sc']">
    <span style="font-variant: small-caps;"><xsl:apply-templates/></span>
  </xsl:template>

  <xsl:template match="tei:hi">
    <span class="tei-hi">
      <xsl:if test="@rend">
        <xsl:attribute name="data-rend"><xsl:value-of select="@rend"/></xsl:attribute>
      </xsl:if>
      <xsl:apply-templates/>
    </span>
  </xsl:template>

  <xsl:template match="tei:emph">
    <em><xsl:apply-templates/></em>
  </xsl:template>

  <!-- ═══════════════════════════════════════════════════════════════════════ -->
  <!-- Named entities                                                          -->
  <!-- ═══════════════════════════════════════════════════════════════════════ -->

  <xsl:template match="tei:persName">
    <span class="tei-persname"><xsl:apply-templates/></span>
  </xsl:template>

  <xsl:template match="tei:placeName">
    <span class="tei-placename"><xsl:apply-templates/></span>
  </xsl:template>

  <xsl:template match="tei:orgName">
    <span class="tei-orgname"><xsl:apply-templates/></span>
  </xsl:template>

  <xsl:template match="tei:date">
    <span class="tei-date">
      <xsl:if test="@when or @from">
        <xsl:attribute name="title">
          <xsl:choose>
            <xsl:when test="@when"><xsl:value-of select="@when"/></xsl:when>
            <xsl:when test="@from and @to">
              <xsl:value-of select="@from"/> &#x2013; <xsl:value-of select="@to"/>
            </xsl:when>
            <xsl:when test="@from"><xsl:value-of select="@from"/></xsl:when>
          </xsl:choose>
        </xsl:attribute>
      </xsl:if>
      <xsl:apply-templates/>
    </span>
  </xsl:template>

  <!-- ═══════════════════════════════════════════════════════════════════════ -->
  <!-- Textual criticism                                                       -->
  <!-- ═══════════════════════════════════════════════════════════════════════ -->

  <xsl:template match="tei:gap">
    <span class="tei-gap">
      <xsl:choose>
        <xsl:when test="@reason = 'illegible'">[ill.]</xsl:when>
        <xsl:when test="@reason = 'lost'">[lost]</xsl:when>
        <xsl:otherwise>[&#x2026;]</xsl:otherwise>
      </xsl:choose>
    </span>
  </xsl:template>

  <xsl:template match="tei:supplied">
    <span class="tei-supplied">[<xsl:apply-templates/>]</span>
  </xsl:template>

  <xsl:template match="tei:unclear">
    <span class="tei-unclear" title="lettura incerta"><xsl:apply-templates/></span>
  </xsl:template>

  <xsl:template match="tei:del">
    <del class="tei-del"><xsl:apply-templates/></del>
  </xsl:template>

  <xsl:template match="tei:add">
    <span class="tei-add">
      <xsl:if test="@place">
        <xsl:attribute name="title">aggiunta: <xsl:value-of select="@place"/></xsl:attribute>
      </xsl:if>
      <xsl:apply-templates/>
    </span>
  </xsl:template>

  <!-- choice: prefer regularised / corrected form -->
  <xsl:template match="tei:choice">
    <xsl:choose>
      <xsl:when test="tei:reg">
        <span class="tei-normalized" title="{tei:orig}"><xsl:apply-templates select="tei:reg"/></span>
      </xsl:when>
      <xsl:when test="tei:corr">
        <span class="tei-normalized" title="{tei:sic}"><xsl:apply-templates select="tei:corr"/></span>
      </xsl:when>
      <xsl:otherwise><xsl:apply-templates/></xsl:otherwise>
    </xsl:choose>
  </xsl:template>

  <!-- Suppress the original/sic when inside a choice already handled above -->
  <xsl:template match="tei:choice/tei:orig | tei:choice/tei:sic"/>

  <xsl:template match="tei:orig | tei:sic">
    <xsl:apply-templates/>
  </xsl:template>

  <xsl:template match="tei:reg | tei:corr">
    <span class="tei-normalized"><xsl:apply-templates/></span>
  </xsl:template>

  <!-- ═══════════════════════════════════════════════════════════════════════ -->
  <!-- Abbreviations                                                           -->
  <!-- ═══════════════════════════════════════════════════════════════════════ -->

  <xsl:template match="tei:abbr">
    <abbr class="tei-abbr">
      <xsl:if test="following-sibling::tei:expan | ../tei:expan">
        <xsl:attribute name="title">
          <xsl:value-of select="following-sibling::tei:expan | ../tei:expan"/>
        </xsl:attribute>
      </xsl:if>
      <xsl:apply-templates/>
    </abbr>
  </xsl:template>

  <xsl:template match="tei:expan">
    <span class="tei-expan"><xsl:apply-templates/></span>
  </xsl:template>

  <!-- ═══════════════════════════════════════════════════════════════════════ -->
  <!-- Notes — emit a superscript marker; full text collected at end of text  -->
  <!-- ═══════════════════════════════════════════════════════════════════════ -->

  <xsl:template match="tei:note">
    <xsl:if test="normalize-space(.) != ''">
      <span class="tei-note-marker">
        <xsl:for-each select="//tei:note[normalize-space(.) != '']">
          <xsl:if test="generate-id(.) = generate-id(current())">
            <xsl:value-of select="position()"/>
          </xsl:if>
        </xsl:for-each>
      </span>
    </xsl:if>
  </xsl:template>

  <!-- ═══════════════════════════════════════════════════════════════════════ -->
  <!-- References and titles                                                   -->
  <!-- ═══════════════════════════════════════════════════════════════════════ -->

  <xsl:template match="tei:ref[@target]">
    <a href="{@target}" class="tei-ref"><xsl:apply-templates/></a>
  </xsl:template>

  <xsl:template match="tei:ref">
    <span class="tei-ref"><xsl:apply-templates/></span>
  </xsl:template>

  <xsl:template match="tei:title[parent::tei:titleStmt]">
    <!-- Inline title inside titleStmt: just output text -->
    <xsl:apply-templates/>
  </xsl:template>

  <xsl:template match="tei:title">
    <cite class="tei-title-inline"><xsl:apply-templates/></cite>
  </xsl:template>

  <!-- ═══════════════════════════════════════════════════════════════════════ -->
  <!-- Default: pass text through; suppress unrecognised element markup       -->
  <!-- ═══════════════════════════════════════════════════════════════════════ -->

  <xsl:template match="*">
    <xsl:apply-templates/>
  </xsl:template>

</xsl:stylesheet>
