import unittest

from pdfcore.pdf_reader import _normalize_ligatures


class TestLigatureNormalization(unittest.TestCase):
    def test_control_code_f_ligatures_midword(self):
        self.assertEqual(_normalize_ligatures("di\x0berential"), "differential")
        self.assertEqual(_normalize_ligatures("coe\x0ecients"), "coefficients")
        self.assertEqual(_normalize_ligatures("in\rection points"), "inflection points")

    def test_word_initial_fi_ligature(self):
        self.assertEqual(_normalize_ligatures("The \x0crst derivative test"), "The first derivative test")
        self.assertEqual(_normalize_ligatures("in\x0cnitesimal"), "infinitesimal")

    def test_unicode_ligature_block(self):
        self.assertEqual(_normalize_ligatures("eﬀort ﬁeld ﬂux"), "effort field flux")

    def test_preserves_structural_control_chars(self):
        # a bare form feed / CR not wedged between letters is left as-is
        self.assertEqual(_normalize_ligatures("page one\x0c\npage two"), "page one\x0c\npage two")
        self.assertEqual(_normalize_ligatures("line one\r\nline two"), "line one\r\nline two")

    def test_empty(self):
        self.assertEqual(_normalize_ligatures(""), "")


if __name__ == "__main__":
    unittest.main()
