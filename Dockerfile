FROM cicirello/pyaction:4

COPY AndroidResourceTranslator.py /AndroidResourceTranslator.py
ENTRYPOINT ["/AndroidResourceTranslator.py"]