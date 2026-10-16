"""Attach answer labels and explicit answers found in each Practice Sheet PDF."""
import json
import re
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).parent
DATA = ROOT / "data" / "questions.json"
QUESTION_MARK = re.compile(
    r"(?im)^[ \t]*(?:\([ \t]*Q[ \t]*(\d{1,4})[ \t]*\)|Q[ \t]*(\d{1,4})[ \t]*[:.)-]|\([ \t]*(\d{1,4})[ \t]*\)(?=[ \t]*(?:\r?$)))\s*"
)
ANSWER = re.compile(
    r"(?i)(?:\b(?:answer\s*key|answer)\s*[:\-]?\s*"
    r"(?:\(\s*([a-e])\s*\)|([a-e]))(?:[ \t]+([^\r\n]{1,100}))?"
    r"|\b(?:hence|therefore|so|thus)[^\r\n.]{0,30}\boption\s*\(?([a-e])\)?)"
)
EQUATION_KEY = re.compile(
    r"(?im)^[ \t]*Q[ \t]*(\d{1,4})[ \t]*:[ \t]*[^\r\n=]*=[ \t]*"
    r"([+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*$"
)


def main():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    total = keyed = matched = 0
    for chapter in data["chapters"]:
        for sheet in chapter["sheets"]:
            source = ROOT / sheet["source"]
            reader = PdfReader(str(source))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            candidates = list(QUESTION_MARK.finditer(text))
            # Keep coherent question-number runs and allow a second run when
            # worked solutions repeat the question numbers after the questions.
            marks = []
            expected = 1
            for candidate in candidates:
                number = int(next(group for group in candidate.groups() if group))
                if number == expected:
                    marks.append(candidate)
                    expected += 1
                elif number == 1 and expected > 1:
                    marks.append(candidate)
                    expected = 2
            keys = {}
            mark_index = 0
            for answer in ANSWER.finditer(text):
                while mark_index + 1 < len(marks) and marks[mark_index + 1].start() < answer.start():
                    mark_index += 1
                if not marks or marks[mark_index].start() > answer.start():
                    continue
                # Ignore unrelated answer mentions far from a numbered problem.
                if answer.start() - marks[mark_index].end() > 6000:
                    continue
                number = int(next(group for group in marks[mark_index].groups() if group))
                label = (answer.group(1) or answer.group(2) or answer.group(4) or "").lower()
                value = (answer.group(3) or "").strip(" .;\t")
                block_end = marks[mark_index + 1].start() if mark_index + 1 < len(marks) else len(text)
                block = text[marks[mark_index].end():block_end]
                explanation = ANSWER.sub("", block, count=1)
                explanation = re.sub(r"6206068272|Complete Maths Subscription", "", explanation, flags=re.I)
                explanation = re.sub(r"\s+", " ", explanation).strip(" :;-\t")
                keys[number] = (label, value, explanation if len(explanation) > 30 else "")

            # Vedic answer lists give a solved equation per Q-number instead of
            # writing "Answer: option"; use its explicit right-hand value.
            for equation_key in EQUATION_KEY.finditer(text):
                number = int(equation_key.group(1))
                keys[number] = ("", equation_key.group(2).replace(",", ""), "")

            by_number = {int(question["number"]): question for question in sheet["questions"]}
            for number, (label, value, explanation) in keys.items():
                question = by_number.get(number)
                if not question:
                    continue
                total += 1
                options = question.get("options") or []
                option_ids = {str(option["id"]).lower() for option in options}
                if label and label in option_ids:
                    question["correctOption"] = label
                    question["correctAnswer"] = None
                    question["answerNote"] = "Answer key in source"
                    keyed += 1
                    matched += 1
                elif value:
                    question["correctOption"] = None
                    question["correctAnswer"] = value
                    question["answerNote"] = "Answer in source"
                    keyed += 1
                    matched += 1
                if explanation:
                    question["explanation"] = explanation

    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Found {total} numbered answer keys; matched {matched} to extracted questions.")
    print(f"Questions now with source answer keys: {keyed}.")


if __name__ == "__main__":
    main()
