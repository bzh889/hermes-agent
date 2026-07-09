"""
onenote_comtypes.py - Direct OneNote COM access via comtypes (no subprocess).

PREREQUISITES:
    pip install comtypes

WORKAROUND for win32com failure:
    OneNote.Application is a vtable-only custom COM interface (IApplication).
    It implements IDispatch but returns 0x8002801D (TYPE_E_LIBNOTREGISTERED) 
    on ALL IDispatch calls. This is because the type library is embedded as a 
    resource in ONENOTE.EXE (resource #3), not a standalone .tlb file.
    
    win32com uses InvokeTypes/Invoke via IDispatch -> fails with 0x8002801D.
    
    comtypes generates vtable bindings from the registered typelib GUID 
    {0EA692EE-BB50-4E3C-AEF0-356D91732725} (version 1.1) which IS registered 
    in HKCR\TypeLib pointing to ONENOTE.EXE\3.
    comtypes.client.GetModule((guid, 1, 1)) uses QueryPathOfRegTypeLib + 
    LoadRegTypeLib (not LoadTypeLibEx), bypassing the EXE resource path issue.
    
    Result: vtable dispatch works perfectly, all methods callable directly in Python.
    
THROUGHPUT (measured on 8686-page OneNote):
    - Typical page: 250-400 KB XML, ~250-280ms per call
    - Rate: ~3.5-5 pages/second (bottleneck: OneNote COM server, not Python)
    - For 8686 pages: approximately 30-40 minutes total
    - piBasic=0 and piBinaryData=1 show identical timing (OneNote reads it all anyway)
"""

import comtypes.client
import xml.etree.ElementTree as ET
import time

# OneNote type library GUID (registered in HKCR\TypeLib, version 1.1)
_TYPELIB_GUID = '{0EA692EE-BB50-4E3C-AEF0-356D91732725}'

def get_onenote():
    """Connect to running OneNote 2016 instance via vtable COM interface.
    
    Returns (onenote_app, mod) where onenote_app has all IApplication methods.
    Call this ONCE and reuse the onenote_app for all subsequent calls.
    """
    mod = comtypes.client.GetModule((_TYPELIB_GUID, 1, 1))
    onenote = comtypes.client.CreateObject('OneNote.Application', interface=mod.IApplication)
    return onenote, mod


def get_all_page_ids(onenote):
    """Return list of (page_id, page_name) tuples from full hierarchy."""
    xml_str = onenote.GetHierarchy('', 4)  # scope=4 = hsPages (all)
    ns = {'one': 'http://schemas.microsoft.com/office/onenote/2013/onenote'}
    root = ET.fromstring(xml_str)
    pages = root.findall('.//one:Page', ns)
    return [(p.get('ID'), p.get('name', 'unknown')) for p in pages]


def get_page_content(onenote, page_id, include_binary=False):
    """Fetch page XML content.
    
    Args:
        onenote: IApplication COM object from get_onenote()
        page_id: OneNote page ID string
        include_binary: if False (default), use piBasic=0 (text only)
    Returns:
        XML string with page content
    """
    return onenote.GetPageContent(page_id, 1 if include_binary else 0, 2)


if __name__ == '__main__':
    print('Connecting to OneNote via comtypes vtable interface...')
    onenote, mod = get_onenote()
    print('Connected!')

    print('Loading hierarchy (all pages)...')
    t0 = time.perf_counter()
    pages = get_all_page_ids(onenote)
    t_hier = time.perf_counter() - t0
    print(f'Total pages: {len(pages)} (loaded in {t_hier:.2f}s)')

    print('\nBenchmarking first 10 pages:')
    times = []
    for page_id, name in pages[:10]:
        t0 = time.perf_counter()
        content = get_page_content(onenote, page_id)
        elapsed = time.perf_counter() - t0
        times.append(elapsed)
        print(f'  {name[:40]}: {elapsed*1000:.0f}ms, {len(content):,} chars')

    avg_ms = sum(times) / len(times) * 1000
    rate = len(times) / sum(times)
    print(f'\nAvg: {avg_ms:.0f}ms/page, Rate: {rate:.2f} pages/sec')
    print(f'Est. for {len(pages)} pages: {len(pages)/rate/60:.0f} minutes')
