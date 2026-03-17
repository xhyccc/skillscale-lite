# Makefile for SkillScale Lite ACM/IFIP conference paper
#
# Requirements: TeX Live (pdflatex, bibtex) or MiKTeX
#   macOS:   brew install --cask mactex
#   Ubuntu:  apt install texlive-full
#
# Usage:
#   make          - build PDF (main.pdf)
#   make clean    - remove build artifacts
#   make distclean - remove all generated files including PDF

MAIN   = main
LATEX  = pdflatex
BIBTEX = bibtex
FLAGS  = -interaction=nonstopmode -halt-on-error

.PHONY: all clean distclean

all: $(MAIN).pdf

$(MAIN).pdf: $(MAIN).tex references.bib
	$(LATEX) $(FLAGS) $(MAIN)
	$(BIBTEX) $(MAIN)
	$(LATEX) $(FLAGS) $(MAIN)
	$(LATEX) $(FLAGS) $(MAIN)

clean:
	rm -f $(MAIN).aux $(MAIN).bbl $(MAIN).blg $(MAIN).log \
	       $(MAIN).out $(MAIN).toc $(MAIN).fls $(MAIN).fdb_latexmk \
	       $(MAIN).synctex.gz

distclean: clean
	rm -f $(MAIN).pdf
