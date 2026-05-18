# Extendable question banks

Drop additional CSV files in this directory to extend the CKAD full question bank.

Requirements:
- use the same CSV schema as `ckad_full_question_bank.csv`
- every question must have a unique `id`
- do not duplicate an `id` that already exists in the base bank or another extension file

These extension files are loaded automatically in drill mode and exam mode.
