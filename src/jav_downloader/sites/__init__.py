"""Site registry for featured and compatibility-only URL adapters."""

from __future__ import annotations

from . import hanime1, jabletv, javguru, missav, spankbang, supjav
from .legacy import sites_91porn, sites_javdb


FEATURED_SITE_CLASSES = (
    jabletv.SiteJableTV,
    jabletv.SiteJableTV_Backup,
    missav.SiteMissAV,
    supjav.SiteSupJav,
    hanime1.SiteHanime1,
    javguru.SiteJavGuru,
    spankbang.SiteSpankBang,
)

LEGACY_URL_ONLY_SITE_CLASSES = (
    sites_91porn.SiteJableOrg,
    sites_91porn.SiteThisAV,
    sites_91porn.SitePigAV,
    sites_91porn.SitePorn5F,
    sites_91porn.Site85Tube,
    sites_91porn.Site91Porn,
    sites_91porn.SitePornBest,
    sites_javdb.SiteJavdbLive,
    sites_javdb.SiteHAnimeXYZ,
    sites_javdb.SitePornTW,
    sites_javdb.SitePornJP,
    sites_javdb.SitePornHK,
    sites_javdb.SitePornHoHo,
    sites_javdb.SitePornNVR,
    sites_javdb.SiteVideo01,
    sites_javdb.SitePornLuLu,
    sites_javdb.SiteMIEN321,
    sites_javdb.SiteAApp11,
    sites_javdb.SiteSeselah,
    sites_javdb.SiteXJISHI,
)

# Backward-compatible public names used throughout the original application.
siteList = FEATURED_SITE_CLASSES + LEGACY_URL_ONLY_SITE_CLASSES


def validate_url(url):
    for site in siteList:
        if site.validate_url(url):
            return site
    return None


def VaildateUrl(url):  # noqa: N802 - legacy API typo retained for v2 callers
    return validate_url(url)


def create_site(
        url, savepath="", silence=False, max_workers=None,
        cut_start=None, cut_end=None, cuts=None,
        audio_fade=False, audio_loudnorm=False,
        encode=None, encode_codec=None, encode_crf=None,
        encode_max_height=None, encode_output_mode=None,
        encode_preset=None, encode_threads=None,
        encode_engine=None, encode_hardware_bitrate_kbps=None,
        encode_hardware_gop=None, encode_hardware_bitrate_mode=None,
        audio_mute=False, audio_bitrate=None, audio_volume=None):
    site = validate_url(url)
    if site is None:
        return None
    kwargs = {
        'savepath': savepath,
        'silence': silence,
        'cut_start': cut_start,
        'cut_end': cut_end,
        'cuts': cuts,
        'audio_fade': audio_fade,
        'audio_loudnorm': audio_loudnorm,
        'audio_mute': audio_mute,
        'audio_bitrate': audio_bitrate,
        'audio_volume': audio_volume,
        'encode': encode,
        'encode_codec': encode_codec,
        'encode_crf': encode_crf,
        'encode_max_height': encode_max_height,
        'encode_output_mode': encode_output_mode,
        'encode_preset': encode_preset,
        'encode_threads': encode_threads,
        'encode_engine': encode_engine,
        'encode_hardware_bitrate_kbps': encode_hardware_bitrate_kbps,
        'encode_hardware_gop': encode_hardware_gop,
        'encode_hardware_bitrate_mode': encode_hardware_bitrate_mode,
    }
    if max_workers is not None:
        kwargs['max_workers'] = max_workers
    return site(url, **kwargs)


def CreateSite(  # noqa: N802
        url, savepath="", silence=False, max_workers=None,
        cut_start=None, cut_end=None, cuts=None,
        audio_fade=False, audio_loudnorm=False,
        encode=None, encode_codec=None, encode_crf=None,
        encode_max_height=None, encode_output_mode=None,
        encode_preset=None, encode_threads=None,
        encode_engine=None, encode_hardware_bitrate_kbps=None,
        encode_hardware_gop=None, encode_hardware_bitrate_mode=None,
        audio_mute=False, audio_bitrate=None, audio_volume=None):
    return create_site(
        url, savepath, silence, max_workers, cut_start, cut_end, cuts,
        audio_fade, audio_loudnorm,
        encode, encode_codec, encode_crf, encode_max_height,
        encode_output_mode, encode_preset, encode_threads,
        encode_engine, encode_hardware_bitrate_kbps,
        encode_hardware_gop, encode_hardware_bitrate_mode,
        audio_mute, audio_bitrate, audio_volume)


