#!/usr/bin/env python3
"""
Batch YouTube Channel Archive Script for GitHub Actions
Supports rate limiting, resume, cookie authentication, and structured output
"""

import os
import json
import sys
import subprocess
import time
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

try:
    import yt_dlp
except ImportError:
    print("Installing yt-dlp...")
    subprocess.run([sys.executable, "-m", "pip", "install", "yt-dlp"], check=True)
    import yt_dlp

try:
    from youtube_transcript_api import YouTubeTranscriptApi
except ImportError:
    print("Installing youtube-transcript-api...")
    subprocess.run([sys.executable, "-m", "pip", "install", "youtube-transcript-api"], check=True)
    from youtube_transcript_api import YouTubeTranscriptApi


def extract_video_id(url_or_id: str) -> str:
    """Extract video ID from URL or return ID if already in ID format."""
    import re
    url_or_id = url_or_id.strip()
    patterns = [
        r'(?:v=|youtu\.be/|shorts/|embed/|live/)([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$',
    ]
    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)
    return url_or_id


def format_timestamp(seconds: float) -> str:
    total = int(seconds)
    h, remainder = divmod(total, 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def fetch_transcript(video_id: str, languages: List[str] = None) -> List[Dict]:
    """Fetch transcript for a video."""
    api = YouTubeTranscriptApi()
    if languages:
        result = api.fetch(video_id, languages=languages)
    else:
        result = api.fetch(video_id)

    return [
        {"text": seg.text, "start": seg.start, "duration": seg.duration}
        for seg in result
    ]


def build_chapters(segments: List[Dict], max_chapters: int = 15) -> List[Dict]:
    """Simple chapter detection based on time gaps."""
    if not segments:
        return []

    chapters = []
    current_start = segments[0]["start"]
    current_texts = [segments[0]["text"]]

    for i in range(1, len(segments)):
        gap = segments[i]["start"] - (segments[i-1]["start"] + segments[i-1]["duration"])
        # Chapter break: gap > 30s or every ~3 minutes
        if gap > 30 or (segments[i]["start"] - current_start) > 180:
            chapters.append({
                "start": current_start,
                "end": segments[i-1]["start"] + segments[i-1]["duration"],
                "text": " ".join(current_texts)
            })
            current_start = segments[i]["start"]
            current_texts = [segments[i]["text"]]
        else:
            current_texts.append(segments[i]["text"])

    # Last chapter
    chapters.append({
        "start": current_start,
        "end": segments[-1]["start"] + segments[-1]["duration"],
        "text": " ".join(current_texts)
    })

    return chapters[:max_chapters]


def generate_markdown(video_id: str, url: str, segments: List[Dict], chapters: List[Dict], language: str = "ko") -> str:
    """Generate structured Markdown for archiving."""
    today = datetime.now().strftime("%Y-%m-%d")
    duration_str = format_timestamp(segments[-1]["start"] + segments[-1]["duration"]) if segments else "0:00"
    full_text = " ".join(seg["text"] for seg in segments)

    md = f"""# YouTube Archive: {video_id}

**원본 URL**: {url}
**비디오 ID**: {video_id}
**아카이빙 일시**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**자막 언어**: {language}
**총 길이**: {duration_str}
**세그먼트 수**: {len(segments)}

---

## 📋 요약 (자동 생성)

{full_text[:500]}...

---

## 📚 챕터별 구조

"""
    for i, ch in enumerate(chapters, 1):
        md += f"### {i}. {format_timestamp(ch['start'])} ~ {format_timestamp(ch['end'])}\n\n{ch['text'][:300]}...\n\n"

    md += "---\n\n## 📝 전체 자막 (타임스탬프 포함)\n\n"

    for seg in segments:
        md += f"{format_timestamp(seg['start'])} {seg['text']}\n"

    md = f"""---
{md}
## 🏷️ 메타데이터

- **source**: youtube
- **video_id**: {video_id}
- **archived_at**: {datetime.now().isoformat()}
- **tags**: [youtube, archive, auto-generated]
- **length_seconds**: {int(segments[-1]['start'] + segments[-1]['duration']) if segments else 0}

"""
    return md


def get_channel_videos(channel_url: str, cookies_file: Optional[str] = None) -> List[Dict]:
    """Extract all video IDs from a channel's uploads playlist."""
    ydl_opts = {
        'extract_flat': 'in_playlist',
        'quiet': True,
        'skip_download': True,
    }
    if cookies_file:
        ydl_opts['cookiefile'] = cookies_file

    videos = []
    with yt_dlp.YoutubeDL({'quiet': True, 'extract_flat': 'in_playlist', 'cookiefile': cookies_file} if cookies_file else {'quiet': True, 'extract_flat': 'in_playlist'}) as ydl:
        # Get channel info to find uploads playlist
        channel_base = f"https://www.youtube.com/@{channel_url.split('@')[-1].split('?')[0]}"
        channel_info = yt_dlp.YoutubeDL({'quiet': True, 'cookiefile': cookies_file} if cookies_file else {'quiet': True}).extract_info(
            channel_base,
            download=False
        )

        if not channel_info:
            raise ValueError("채널 정보를 가져올 수 없습니다.")

        channel_id = channel_info.get('id')
        if not channel_id:
            raise ValueError("채널 ID를 찾을 수 없습니다.")

        # Uploads playlist ID is UC -> UU
        if channel_id.startswith('UC'):
            uploads_id = 'UU' + channel_id[2:]
        else:
            uploads_id = 'UU' + channel_id

        print(f"채널 ID: {channel_id}, 업로드 플레이리스트: {uploads_id}")

        # Extract from uploads playlist
        playlist_url = f"https://www.youtube.com/playlist?list={uploads_id}"
        ydl_opts = {'extract_flat': 'in_playlist', 'quiet': True}
        if cookies_file:
            ydl_opts['cookiefile'] = cookies_file

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            playlist = ydl.extract_info(f"https://www.youtube.com/playlist?list={uploads_id}", download=False)

            if 'entries' in playlist:
                for entry in playlist['entries']:
                    if entry and entry.get('id'):
                        videos.append({
                            'id': entry['id'],
                            'title': entry.get('title', '제목 없음'),
                            'url': f"https://www.youtube.com/watch?v={entry['id']}"
                        })

        print(f"총 {len(videos)}개 영상 발견")
        return videos


def process_video(video_id: str, output_dir: Path, languages: List[str] = None) -> Dict[str, Any]:
    """Process a single video: fetch transcript, generate markdown, save."""
    video_id = video_id.strip()
    url = f"https://www.youtube.com/watch?v={video_id}"

    try:
        # Fetch transcript
        segments = fetch_transcript(video_id, languages)
        if not segments:
            return {"success": False, "error": "자막 없음"}

        # Build chapters
        chapters = build_chapters(segments)

        # Generate markdown
        md = generate_markdown(video_id, f"https://www.youtube.com/watch?v={video_id}",
                              segments, chapters)

        # Save markdown
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{video_id}.md"
        filepath = Path(output_dir) / filename

        filepath.write_text(md, encoding='utf-8')

        return {
            "success": True,
            "video_id": video_id,
            "filepath": str(filepath),
            "segments": len(segments),
            "chapters": len(chapters)
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Batch YouTube Channel Archive")
    parser.add_argument("--channel-url", required=True, help="YouTube channel URL (e.g., https://youtube.com/@channelname)")
    parser.add_argument("--rate-limit", type=int, default=2, help="Requests per minute (default: 2)")
    parser.add_argument("--max-videos", type=int, default=100, help="Max videos to process per run")
    parser.add_argument("--output-dir", default="./archive_output", help="Output directory")
    parser.add_argument("--language", default="ko,en", help="Comma-separated language codes")
    parser.add_argument("--resume", action="store_true", help="Resume from last position")
    parser.add_argument("--cookies-file", help="Path to YouTube cookies file (Netscape format)")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # State file for resume capability
    state_file = Path(args.output_dir) / "progress_state.json"

    # Load previous state if resuming
    processed_ids = set()
    start_index = 0
    if args.resume and Path("progress_state.json").exists():
        with open("progress_state.json", 'r') as f:
            state = json.load(f)
            start_index = state.get("last_index", 0)
            processed_ids = set(state.get("processed_ids", []))
            print(f"Resuming from index {start_index}, already processed {len(processed_ids)} videos")

    # Get channel videos
    print(f"채널 영상 수집 중: {args.channel_url}")
    videos = get_channel_videos(args.channel_url, args.cookies_file)
    print(f"총 {len(videos)}개 영상 발견")

    # Filter already processed
    remaining_videos = [v for v in videos if v['id'] not in processed_ids]
    print(f"처리 대상: {len(remaining_videos)}개 (이미 처리: {len(videos) - len(remaining_videos)}개)")

    # Limit to max_videos
    to_process = remaining_videos[:args.max_videos]
    print(f"이번 실행 처리: {len(to_process)}개 (최대 {args.max_videos}개)")

    # Rate limiting
    rate_limit = args.rate_limit
    interval = 60.0 / rate_limit if rate_limit > 0 else 0

    # Process videos
    results = []
    success_count = 0
    fail_count = 0

    for i, video in enumerate(to_process):
        video_id = video['id']
        print(f"\n[{i+1}/{len(to_process)}] {video_id} - {video['title'][:60]}...")

        result = process_video(video_id, args.output_dir, args.language.split(','))

        if result["success"]:
            print(f"  ✅ {video_id} - {result['segments']} 세그먼트, {result['chapters']} 챕터")
            success_count += 1
        else:
            print(f"  ❌ {video_id}: {result['error'][:100]}")
            fail_count += 1

        # Save progress
        with open("progress_state.json", 'w') as f:
            json.dump({
                "last_index": i,
                "processed_ids": [v['id'] for v in to_process[:i+1]],
                "success_count": success_count,
                "fail_count": fail_count
            }, f)

        # Save intermediate results
        results_file = Path("archive_output") / "results.json"
        results_file.parent.mkdir(parents=True, exist_ok=True)
        with open(results_file, 'w') as f:
            json.dump({
                "total": len(to_process),
                "processed": i + 1,
                "success": success_count,
                "failed": fail_count,
                "success_rate": f"{success_count/(i+1)*100:.1f}%" if i >= 0 else "0%"
            }, f)

        # Rate limiting with jitter
        if i < len(to_process) - 1:
            sleep_time = 60.0 / args.rate_limit + (0.5 * (i % 3))  # add small jitter
            time.sleep(sleep_time)

    # Final summary
    print(f"\n{'='*50}")
    print(f"완료: 성공 {success_count}개, 실패 {fail_count}개")
    print(f"성공률: {success_count/len(to_process)*100:.1f}%")
    print(f"{'='*50}")

    # Generate summary
    summary = {
        "timestamp": datetime.now().isoformat(),
        "total": len(to_process),
        "success": success_count,
        "failed": fail_count,
        "success_rate": f"{success_count/len(to_process)*100:.1f}%"
    }

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "summary.json", 'w') as f:
        json.dump(summary, f, indent=2)


if __name__ == "__main__":
    main()