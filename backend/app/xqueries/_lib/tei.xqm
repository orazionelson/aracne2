(:~
 : Common helpers for TEI XML documents.
 : Imported by other XQuery modules via:
 :   import module namespace tei="http://aracne2/tei" at "_lib/tei.xqm";
 :)
module namespace tei = "http://aracne2/tei";

declare namespace t = "http://www.tei-c.org/ns/1.0";

(:~ True when the document root is a TEI element. :)
declare function tei:is-tei($doc as document-node()) as xs:boolean {
    exists($doc/t:TEI)
};

(:~ Extract the main title from a TEI titleStmt. Returns empty string if absent. :)
declare function tei:title($doc as document-node()) as xs:string {
    string(($doc//t:titleStmt/t:title)[1])
};

(:~ Extract the first author from a TEI titleStmt. Returns empty string if absent. :)
declare function tei:author($doc as document-node()) as xs:string {
    string(($doc//t:titleStmt/t:author)[1])
};

(:~ Extract the publication date from a TEI publicationStmt. Returns empty string if absent. :)
declare function tei:date($doc as document-node()) as xs:string {
    string(($doc//t:publicationStmt/t:date)[1])
};
