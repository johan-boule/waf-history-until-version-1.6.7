<?xml version='1.0'?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
                version='1.0'
                xmlns="http://www.w3.org/TR/xhtml1/transitional"
                exclude-result-prefixes="#default">

<!-- Change this to the path to where you have installed Norman
     Walsh's XSL stylesheets.  -->
<xsl:import href="/usr/share/xml/docbook/stylesheet/nwalsh/xhtml/docbook.xsl"/>

  <xsl:param name="draft.mode" select="'no'"/>
  <xsl:param name="paper.type" select="'A4'"/>
  <xsl:param name="chapter.autolabel" select="1"></xsl:param>
  <xsl:param name="appendix.autolabel" select="1"></xsl:param>
  <xsl:param name="section.autolabel" select="1"></xsl:param>
  <xsl:param name="section.autolabel.max.depth" select="3"></xsl:param>

<!--   For HTML output, use the standard image size. -->
  <xsl:param name="ignore.image.scaling" select="1"/>

<!-- use this to select the extension for html output across all files. -->
  <xsl:param name="graphic.default.extension" select="'png'"></xsl:param>

  <xsl:param name="hyphenate.verbatim" select="1"></xsl:param>
  <xsl:param name="monospace.font.family" select="'monospace'"></xsl:param>

<xsl:attribute-set name="monospace.verbatim.properties"
                   use-attribute-sets="verbatim.properties monospace.properties">
  <xsl:attribute name="wrap-option">wrap</xsl:attribute>
  <xsl:attribute name="hyphenation-character">&#x21BA;</xsl:attribute>
</xsl:attribute-set>

</xsl:stylesheet>
