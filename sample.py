import sys
import os
import time
import subprocess
import json
import whisper
from pydub import AudioSegment
from pydub.utils import which
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.exceptions import OutputParserException
from pydantic import BaseModel, Field
from typing import TypedDict, Optional
# Configure FFmpeg path
AudioSegment.converter = which("ffmpeg") or r"C:/ffmpeg/bin/ffmpeg.exe"

# Load environment variables
load_dotenv()
groq_api_key = os.getenv("GROQ_API_KEY")

# Initialize Whisper model
whisper_model = whisper.load_model("medium")

# Define Pydantic model for output validation

class IncidentReport(TypedDict):
    PNR: str
    issue: str
    issueType: str
    location: str
    urgency: str
    solution:str
    sentiment:str

# Configure LLM processing chain
system_prompt = """You are an ADOC (Automated Document Processing) operator specializing in extracting structured information from customer complaints at an airport. Your task is to analyze the provided complaint text and extract key details accurately.

Extraction Requirements:
You must extract the following fields:
PNR Number: Extract the Passenger Name Record (PNR) number from the text. The PNR number is typically 6 alphanumeric characters (e.g., "ABC123").
If a valid PNR number is found, extract it.
If no PNR number is present, return "Not specified"

Issue: A concise description of the problem or incident being reported.

Issue Type: Categorization of the issue. Choose from the following categories only. dont take any other categories:

"Baggage handling"
"Check-in and boarding"
"Security"
"Terminal facilities"
"Flight delays and cancellations"
"Customer service"
"Refunds"
"General information"
Location: The location where the incident occurred Choose from the following categories only. dont take any other categories:
"Check-in and Boarding Area"
"Security Checkpoint"
"Baggage Claim"
"Terminal Facilities"
"Gate Area"
and Do not include the airport name.

Urgency: Determine urgency based on the nature of the complaint (DO NOT ask the customer). Use the following guidelines:

Critical: Threats to passenger safety, security breaches, medical emergencies, severe disruptions.
High: Flight delays, baggage lost with critical items (passport, medication), serious passenger dissatisfaction.
Medium: Minor service delays, issues with airport facilities, luggage damage.
Low: General complaints, minor inconveniences, feedback on services.
suggestion: A suggested resolution based on the extracted issue, issue type, location, and urgency level.

Sentiment: Determine the user’s emotional state based on the actual content of the complaint rather than tone, punctuation, or writing style.

Categorize sentiment into one of the following:

Angry 🔴:

The complaint expresses extreme dissatisfaction with clear demands for action.
The issue is severe (e.g., lost baggage with essential items, repeated service failures).
Mentions legal action, compensation requests, or escalation to authorities.
Uses words related to rights violations, serious inconvenience, or unacceptable service.
Frustrated 🟠:

The complaint indicates dissatisfaction but without severe consequences.
Repeated mentions of delays, poor service, or unresolved issues.
Words like "inconvenient," "disappointed," "not satisfied," "waste of time".
No direct escalation threats but clear dissatisfaction.
Anxious/Stressed 🟡:

The complaint involves an urgent personal concern (e.g., lost important items, tight connection times).
Mentions of missing flights, critical documents, medications, or time-sensitive problems.
Uses words like "worried," "urgent," "need help immediately," "please resolve quickly".
Does not focus on dissatisfaction, but rather on the need for immediate resolution.
Neutral 🔵:

The complaint is purely factual without expressing dissatisfaction or urgency.
Simply reports an issue for awareness without demanding compensation or quick action.
No negative or positive emotion is evident in the content.
Example: "The baggage claim area was crowded, and it took 30 minutes to get my bag."
Satisfied 🟢:

The complaint includes positive feedback or an already resolved issue.
Mentions of helpful staff, good service, or a successful resolution.
Words like "thank you," "appreciate," "handled well," "good experience".

Output Format:
Return ONLY a valid JSON object without additional text or explanations: 

### *Output Format*
Return ONLY a valid JSON object:
```json
{{
  "PNR": "extracted PNR number"
  "issue": "extracted issue description",
  "issueType": "categorized issue type",
  "location": "extracted location",
  "urgency": "determined urgency level",
  "suggestion": "proposed solution based on analysis",
  "sentiment": "determined sentiment",
}}




If any field cannot be found in the text, use "Not specified" as the value.

Process the following complaint text and extract the required information:
{call_recording}
"""
class IncidentReport(TypedDict):
    PNR: str
    issue: str
    issueType: str
    location: str
    urgency: str
    suggestion:str
    sentiment:str

parser = JsonOutputParser(pydantic_object=IncidentReport)
qa_prompt = PromptTemplate(
    template=system_prompt,
    input_variables=["call_recording"]
)
llm = ChatGroq(
    model="Gemma2-9b-It",
    groq_api_key=groq_api_key,
    temperature=0.2,
    max_tokens=400
)

chain = qa_prompt | llm | parser

def wait_for_file(file_path, timeout=15):
    """Ensure file is completely written to disk"""
    start_time = time.time()
    last_size = -1
    while time.time() - start_time < timeout:
        try:
            if os.path.exists(file_path):
                current_size = os.path.getsize(file_path)
                if current_size == last_size and current_size > 0:
                    return True
                last_size = current_size
            time.sleep(0.5)
        except OSError:
            time.sleep(0.5)
    raise TimeoutError(f"File {file_path} not stable after {timeout} seconds")

def convert_mkv_to_mp3(mkv_path):
    """Convert MKV file to MP3 using FFmpeg"""
    try:
        mkv_path = os.path.normpath(mkv_path)
        base_name = os.path.splitext(os.path.basename(mkv_path))[0]
        output_dir = os.path.join(os.path.dirname(mkv_path), "mp3_conversions")
        os.makedirs(output_dir, exist_ok=True)
        mp3_path = os.path.join(output_dir, f"{base_name}.mp3")

        ffmpeg_cmd = [
            'ffmpeg',
            '-y',  # Overwrite existing files
            '-i', mkv_path,
            '-vn',  # Disable video
            '-acodec', 'libmp3lame',
            '-b:a', '192k',
            '-loglevel', 'error',
            mp3_path
        ]

        result = subprocess.run(
            ffmpeg_cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        return mp3_path

    except subprocess.CalledProcessError as e:
        error_msg = f"FFmpeg conversion failed: {e.stderr.decode()}"
        raise RuntimeError(error_msg)

def transcribe_audio(file_path):
    """Transcribe audio using Whisper with validation"""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Audio file not found: {file_path}")
    
    if os.path.getsize(file_path) == 0:
        raise ValueError("Empty audio file provided")

    result = whisper_model.transcribe(
        file_path,
        task="translate",
        language="hi",
        fp16=False,
        verbose=False
    )
    
    
    return result["text"].strip()

def process_audio(mkv_file_path):
    """End-to-end audio processing pipeline"""
    try:
        # Stage 1: File validation and conversion
        if not mkv_file_path.endswith('.mkv'):
            raise ValueError("Invalid file format. Only MKV files are supported")
        
        wait_for_file(mkv_file_path)
        mp3_path = convert_mkv_to_mp3(mkv_file_path)
        
        # Stage 2: Audio transcription
        transcript = transcribe_audio(mp3_path)
        if not transcript:
            return {"error": "Empty transcription result"}

        # Stage 3: LLM processing with retries
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = chain.invoke({"call_recording": transcript})
                return response
            except OutputParserException as e:
                if attempt == max_retries - 1:
                    raise
                print(f"Retry {attempt + 1}/{max_retries} - Parsing failed: {str(e)}")
                time.sleep(1)
        
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python process_audio.py <path_to_mkv_file>")
        sys.exit(1)

    input_file = sys.argv[1]
    
    try:
        result = process_audio(input_file)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": f"Critical failure: {str(e)}"}, indent=2))
        sys.exit(1)