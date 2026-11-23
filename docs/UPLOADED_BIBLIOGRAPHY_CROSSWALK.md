# Uploaded bibliography crosswalk

Source file supplied by user: `Biblio_biochar_production_characteristics202404(1).csv` (122 records). A byte-for-byte copy is included as `data/reference_bibliography_uploaded.csv` for provenance. The bibliography is a candidate literature pool, not proof that every record is represented in the model training data. The following selected records have clear relevance to model inputs, feedstock effects or validation planning:

| Uploaded record ID | Study | Relevance | Model use / caution |
|---:|---|---|---|
| 6 | Bian et al. (2016), crop residues in mobile bench-scale pyrolyser, DOI 10.1016/j.jaap.2016.03.018 | Product characterisation and crop-residue experimental data | Candidate external/scale-aware benchmark; harmonise conditions and basis. |
| 13 | Budai et al. (2014), corncob and miscanthus biochar properties, DOI 10.1021/jf501139f | Feedstock and production-method effects | Property-model context; do not infer unreported fields. |
| 23 | Crombie & Mašek (2015), pyrolysis biochar systems, DOI 10.1111/gcbb.12137 | Energy/carbon trade-off | Supports system-level trade-off framing; boundary must match. |
| 24 | Crombie et al. (2013), pyrolysis conditions and biochar stability, DOI 10.1111/gcbb.12030 | Stability methods | Useful for evaluating permanence proxy; does not validate current H/C interpolation. |
| 53 | Kloss et al. (2012), slow-pyrolysis biochars across feedstocks and temperatures, DOI 10.2134/jeq2011.0070 | Multi-feedstock property observations | Candidate ML training/holdout source after extraction. |
| 56 | Lee et al. (2013), biomass residues at 500°C, DOI 10.1016/j.biortech.2013.08.135 | Comparative residue biochar data | Candidate validation source; confirm exact process conditions. |
| 60 | Li et al. (2018), effects of temperature, heating rate, residence time, atmosphere and pressure | Process-feature effects | Candidate source for feature/domain checks; verify DOI metadata in original record. |
| 80 | Rafiq et al. (2016), corn stover biochar, DOI 10.1371/journal.pone.0156894 | Corn-stover property and energy evidence | Candidate feedstock-specific comparison. |
| 11 | Brewer et al. (2009), fast-pyrolysis and gasification biochar characterisation | Process-mode contrast | Supports distinction between process classes; not sufficient for universal yield split. |
| 35 | Fu et al. (2019), biochars and hydrochars from food wastes, DOI 10.1016/j.jclepro.2019.117637 | HTC/hydrochar comparison | Candidate HTC property benchmark; conditions must be matched. |
| 73 | Nakason et al. (2019), torrefaction of agricultural wastes | Torrefaction product properties | Candidate process-specific source; uploaded record has no DOI. |

**Important:** the uploaded bibliography is metadata (authors/title/journal/year/DOI and thematic flags), not a full-text extraction table. The platform must not claim that it trained on or validated against a paper until the corresponding numeric observations, units, dry/wet basis, reactor conditions and provenance have been extracted and linked to the exact source.
