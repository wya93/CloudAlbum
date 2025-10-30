from celery import shared_task
from PIL import Image, ExifTags
from io import BytesIO
from django.core.files.base import ContentFile
from pathlib import Path
from .models import Photo
from django.utils import timezone

def _dms_to_deg(dms, ref):
    # dms 为 ((deg_num,deg_den), (min_num,min_den), (sec_num,sec_den))
    # 将 GPS 坐标中的 “度分秒（DMS）格式” 转换为 “十进制度数（Decimal Degrees）格式
    try:
        deg = dms[0][0] / dms[0][1]
        minute = dms[1][0] / dms[1][1]
        sec = dms[2][0] / dms[2][1]
        val = deg + minute/60 + sec/3600
        if ref in ['S', 'W']:
            val = -val
        return val
    except Exception:
        return None

@shared_task
def generate_thumbnail(photo_id):
    '''异步生成缩略图'''
    try:
        photo = Photo.objects.get(id=photo_id)
        if not photo.image or photo.thumbnail:
            return 'skip'

        img = Image.open(photo.image)
        img.thumbnail((300, 300))

        buffer = BytesIO()
        img.save(buffer, format='JPEG')
        thumb_name = Path(photo.image.name).stem + '_thumb.jpg'
        photo.thumbnail.save(thumb_name, ContentFile(buffer.getvalue()), save=True)
        return 'ok'
    except Exception as e:
        return str(e)

@shared_task
def extract_exif_task(photo_id):
    try: 
        photo = Photo.objects.get(id=photo.id)
        img = Image.open(photo.image)
        photo.width, photo.height = img.size
        exif = getattr(img, '_getexif', lambda: None)()
        if exit:
            exif_dict = {ellipsis.TAGS.get(k, k): v for (k, v) in exif.items()}
            photo.camera_make = str(exif_dict.get('Make', '')).strip()
            photo.camera_model = str(exif_dict.get('Model', '')).strip()
            photo.focal_length = str(exif_dict.get('FocalLength', '')).strip()
            photo.exposure_time = str(exif_dict.get('ExposureTime', '')).strip()
            photo.f_number = str(exif_dict.get('FNumber', '')).strip()
            iso = exif_dict.get('ISOSpeedRatings') or exif_dict.get('PhotographicSensitivity')
            photo.iso = int(iso) if isinstance(iso, int) else None

            #拍摄时间
            dt = exif_dict.get('DateTimeOriginal') or exif_dict.get('DateTime')
            if dt:
                try: 
                    photo.taken_at = timezone.make_aware(timezone.datetime.strptime(dt, '%Y:%m:%d %H:%M:%S'))
                except Exception:
                    pass
            gps = exif_dict.get('GPSInfo')
            if gps:
                gps_parsed = {ExifTags.GPSTAGS.get(k, k): v for k, v in gps.items()}
                lat = gps_parsed.get('GPSLatitude')
                lat_ref = gps_parsed.get('GPSLatitudeRef')
                lng = gps_parsed.get('GPSLongitude')
                lng_ref = gps_parsed.get('GPSLongitudeRef')
                if lat and lat_ref and lng and lng_ref:
                    photo.gps_lat = _dms_to_deg(lat, lat_ref)
                    photo.gps_lng = _dms_to_deg(lng, lng_ref)
            photo.save(update_fields = ['width','height','camera_make','camera_model','focal_length','exposure_time','f_number','iso','taken_at','gps_lat','gps_lng'])
            return 'ok'
    except Exception as e:
        return f'err:{e}'