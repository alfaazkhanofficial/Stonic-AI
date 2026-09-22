"""Live xKiro acceptance using synthetic content only; credentials never enter output."""
import asyncio
import base64
import io
import json
import sys
import httpx
import re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from PIL import Image, ImageDraw, ImageFont
from stonic.config.settings import Settings
from stonic.providers.llm import OpenAICompatibleProvider
from stonic.providers.vision import Vision, VisionRequest
from stonic.security.secrets import SecretStore


async def main():
    provider=OpenAICompatibleProvider(SecretStore(ROOT/'data'))
    try:
        check=await provider.check(Settings())
        if check.status == "unconfigured":
            print(json.dumps({"status":"skipped","detail":check.detail}),flush=True)
            return
        if check.status != "ready":
            raise RuntimeError(check.detail)
        parts=[]
        async for piece in provider.stream(Settings(),[{'role':'user','content':'Reply with one short sentence saying STONIC STREAM 319 is verified. Do not use tools.'}]):
            parts.append(piece)
        assert len(parts)>1 and '319' in ''.join(parts)
        picture=Image.new('RGB',(800,260),'white');draw=ImageDraw.Draw(picture)
        font=ImageFont.truetype(r'C:\Windows\Fonts\arial.ttf',40)
        draw.text((25,20),'STONIC TEST 8421',font=font,fill='black')
        draw.ellipse((30,95,155,220),fill='blue');draw.rectangle((210,105,380,205),fill='red')
        buffer=io.BytesIO();picture.save(buffer,format='PNG')
        result=await Vision(provider,ROOT/'.runtime/live-vision').process(VisionRequest(
            image='data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode(),mode='analyze',consent_to_upload=True,
            question='Read the four-digit number and identify the color of the circle and rectangle. One sentence.'))
        answer=result.data['text'].lower()
        assert result.success and '8421' in answer and 'blue' in answer and 'red' in answer
        report={'xkiro_stream':'passed','content_chunks':len(parts),'synthetic_image_understanding':'passed','raw_screenshot_uploaded':False}
        (ROOT/'.runtime/live-intelligence-acceptance.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report),flush=True)
    except httpx.HTTPStatusError as error:
        response=error.response
        payload=response.json().get('error',{})
        print(json.dumps({'status':response.status_code,'code':payload.get('code'),'type':payload.get('type'),
            'retry_after':response.headers.get('retry-after'),'token_remaining':response.headers.get('x-ratelimit-remaining-tokens'),
            'token_reset':response.headers.get('x-ratelimit-reset-tokens'),'numbers':re.findall(r'(?:Limit|Requested|Used)[: ]+(\d+)',str(payload.get('message',''))),'message':str(payload.get('message','')).split('organization')[0][:250]}),flush=True)
        raise SystemExit(2)
    finally:await provider.close()


if __name__=='__main__':asyncio.run(main())
