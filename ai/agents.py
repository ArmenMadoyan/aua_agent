from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from ai.config import API_KEY
from ai.course_tools import create_course_pdf, create_powerpoint_deck
from ai.tools import retrieve_from_knowledge_base

llm = ChatOpenAI(
    model_name="gpt-4.1",
    openai_api_key=API_KEY,
    temperature=0,
)

kb_agent = create_agent(
    model=llm,
    tools=[retrieve_from_knowledge_base],
    system_prompt=(
        "You are a helpful assistant for the American University of Armenia (AUA). "
        "You answer questions using the AUA policy PDF knowledge base via the "
        "`retrieve_from_knowledge_base` tool. Use the tool when the user asks about "
        "AUA policies, procedures, rules, academic matters, HR, facilities, admissions, "
        "conduct, or any official AUA information. If the question is about general "
        "knowledge or unrelated to AUA, you may answer without the tool. Always cite "
        "the policy document (file name) when you use retrieved content. Prioritize "
        "accuracy and base answers on the retrieved policy text when relevant."
    ),
)

course_llm = ChatOpenAI(
    model_name="gpt-4.1",
    openai_api_key=API_KEY,
    temperature=0.35,
)

course_agent = create_agent(
    model=course_llm,
    tools=[create_powerpoint_deck, create_course_pdf],
    system_prompt=(
        "You help instructors prepare course materials. When the user wants slides, "
        "you MUST call `create_powerpoint_deck` with a short deck_title and slides_text "
        "in this exact pattern: each slide starts with a line 'SLIDE: Title' then lines "
        "with bullets starting with '- '. Build substantive content from the user's "
        "syllabus, topic list, or instructions. "
        "When the user wants homework, quizzes, a midterm, a final, or any written "
        "assessment as a file, you MUST call `create_course_pdf` with document_type "
        "(homework, quiz, midterm, final_exam, or other), title, and a full body with "
        "questions and instructions in plain text (sections separated by blank lines). "
        "Never paste a full exam or homework only as chat text when they asked for a file—use the tool. "
        "If the request is vague (e.g. 'make course content' without saying slides vs "
        "exams), ask briefly what they need and which topics or syllabus to use—then "
        "use the tools once you know. After each tool call, tell the user the filename "
        "and that they can download it from the /course/artifacts/ URL path on the API."
    ),
)
