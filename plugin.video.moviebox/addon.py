import sys
import os
import time
import uuid
import json
import base64
import hashlib
import hmac
import urllib.request
import urllib.parse
import urllib.error
import xbmcgui
import xbmcplugin
import xbmcaddon
import xbmcvfs
import ssl
import xbmc

# Configurações do Kodi
ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')
PLUGIN_URL = sys.argv[0]
HANDLE = int(sys.argv[1])

# Configuração de persistência (salvar último filme e série separadamente)
PROFILE_PATH = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
LAST_ITEM_FILE = os.path.join(PROFILE_PATH, 'last_item.json')

def save_last_item(subject_id, title, cover_url="", subject_type=1):
    """Salva o último filme ou série acessado separadamente."""
    try:
        if not os.path.exists(PROFILE_PATH):
            os.makedirs(PROFILE_PATH)

        data = load_last_item()
        if not isinstance(data, dict):
            data = {}

        item_data = {
            'subject_id': str(subject_id),
            'title': str(title),
            'cover_url': str(cover_url)
        }

        # Separa o armazenamento entre Filme (1) e Série (2)
        if int(subject_type) == 1:
            data['movie'] = item_data
        else:
            data['series'] = item_data

        with open(LAST_ITEM_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception as e:
        xbmc.log(f"[MovieBox API] Erro ao salvar último item: {e}", xbmc.LOGERROR)

def load_last_item():
    """Carrega as informações salvas do filme e da série."""
    try:
        if os.path.exists(LAST_ITEM_FILE):
            with open(LAST_ITEM_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
    except Exception as e:
        xbmc.log(f"[MovieBox API] Erro ao carregar último item: {e}", xbmc.LOGERROR)
    return {}

# ==========================================
# CLASSE DA API MOVIEBOX
# ==========================================
class MovieBoxPlayerAPI:
    def __init__(self):
        self.hosts = [
            "https://api6.aoneroom.com",
            "https://api5.aoneroom.com",
            "https://api4.aoneroom.com",
            "https://api.inmoviebox.com",
        ]
        self.active_host_index = 0
        self.secret_key_base64 = "76iRl07s0xSN9jqmEWAt79EBJZulIQIsV64FZr2O"
        self.runtime_token = None
        
        self.user_agent = "com.community.oneroom/50020042 (Linux; U; Android 9; en_US; Redmi 23078RKD5C; Build/PQ3A.190605.03081104; Cronet/135.0.7012.3)"
        
        self.client_info = json.dumps({
            "package_name": "com.community.oneroom",
            "version_name": "3.0.03.0529.03",
            "version_code": 50020042,
            "os": "android",
            "os_version": "9",
            "install_ch": "ps",
            "device_id": os.urandom(16).hex(),
            "install_store": "ps",
            "gaid": str(uuid.uuid4()),
            "brand": "Redmi",
            "model": "23078RKD5C",
            "system_language": "en",
            "net": "NETWORK_WIFI",
            "region": "US",
            "timezone": "America/New_York",
            "sp_code": "40401",
            "X-Play-Mode": "2"
        }, separators=(',', ':'))
        self.spoofed_ip = "103.241.120.45"

    def _get_secret_bytes(self):
        padded = self.secret_key_base64
        padding = (4 - (len(padded) % 4)) % 4
        padded += "=" * padding
        return base64.b64decode(padded)

    def _generate_x_client_token(self, ts):
        ts_str = str(ts)
        reversed_ts = ts_str[::-1]
        hash_val = hashlib.md5(reversed_ts.encode('utf-8')).hexdigest()
        return f"{ts_str},{hash_val}"

    def _generate_signature(self, method, url, body_str, ts):
        parsed_url = urllib.parse.urlparse(url)
        query_params = urllib.parse.parse_qsl(parsed_url.query, keep_blank_values=True)
        query_params.sort(key=lambda x: x[0])
        query_parts = [f"{k}={v}" for k, v in query_params]
        
        canonical_url = parsed_url.path
        if query_parts:
            canonical_url = f"{parsed_url.path}?{'&'.join(query_parts)}"

        body_hash = ""
        body_length = ""
        
        if body_str:
            body_bytes = body_str.encode('utf-8')
            body_length = str(len(body_bytes))
            body_hash = hashlib.md5(body_bytes[:102400]).hexdigest()

        canonical_str = f"{method.upper()}\napplication/json\napplication/json\n{body_length}\n{ts}\n{body_hash}\n{canonical_url}"
        
        mac = hmac.new(self._get_secret_bytes(), canonical_str.encode('utf-8'), hashlib.md5)
        signature = base64.b64encode(mac.digest()).decode('utf-8')
        
        return f"{ts}|2|{signature}"

    def _build_headers(self, method, url, body_str=None):
        ts = int(time.time() * 1000)
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Client-Token": self._generate_x_client_token(ts),
            "x-tr-signature": self._generate_signature(method, url, body_str, ts),
            "X-Client-Info": self.client_info,
            "X-Client-Status": "0",
            "X-Forwarded-For": self.spoofed_ip
        }

        if self.runtime_token:
            headers["Authorization"] = f"Bearer {self.runtime_token}"

        return headers

    def _absorb_x_user(self, response_headers):
        x_user = response_headers.get("x-user")
        if x_user:
            try:
                json_data = json.loads(x_user)
                if "token" in json_data:
                    self.runtime_token = json_data["token"]
            except Exception:
                pass

    def init_api(self):
        path = "/wefeed-mobile-bff/tab-operating?page=1&tabId=0&version="
        self.get(path)

    def request(self, method, path, body_str=None):
        if not self.runtime_token and "tab-operating" not in path:
            try:
                self.init_api()
            except Exception as e:
                xbmc.log(f"[MovieBox API] Falha na inicialização do token: {e}", xbmc.LOGWARNING)

        retry_status_codes = [403, 406, 407, 429, 500, 502, 503, 504]
        start_idx = self.active_host_index
        
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        for i in range(len(self.hosts)):
            idx = (start_idx + i) % len(self.hosts)
            base_url = self.hosts[idx]
            full_url = f"{base_url}{path}"

            headers = self._build_headers(method, full_url, body_str)
            
            req = urllib.request.Request(full_url, headers=headers, method=method)
            if body_str:
                req.data = body_str.encode('utf-8')

            try:
                with urllib.request.urlopen(req, timeout=10, context=ctx) as response:
                    self._absorb_x_user(response.headers)
                    response_data = response.read().decode('utf-8')
                    json_data = json.loads(response_data)
                    
                    self.active_host_index = idx
                    return json_data.get("data", json_data)
                    
            except urllib.error.HTTPError as e:
                erro_body = e.read().decode('utf-8') if e.fp else "Sem corpo"
                xbmc.log(f"[MovieBox API] HTTPError {e.code} no host {base_url}: {erro_body}", xbmc.LOGERROR)
                
                if e.code in retry_status_codes:
                    continue
            except urllib.error.URLError as e:
                xbmc.log(f"[MovieBox API] URLError no host {base_url}: {e.reason}", xbmc.LOGERROR)
                continue
            except Exception as e:
                xbmc.log(f"[MovieBox API] Erro desconhecido: {str(e)}", xbmc.LOGERROR)
                continue
                
        raise Exception("Servidores indisponíveis.")

    def get(self, path):
        return self.request("GET", path)

    def post(self, path, payload):
        body_str = json.dumps(payload, separators=(',', ':'))
        return self.request("POST", path, body_str)

    def search(self, query, page=1):
        payload = {
            "keyword": query,
            "page": page,
            "perPage": 20,
            "subjectType": "All",
            "tabId": "All"
        }
        res = self.post("/wefeed-mobile-bff/subject-api/search/v2", payload)
        return self.parse_search_results(res)

    def parse_search_results(self, response):
        if not response: return []
        
        if "list" in response and isinstance(response["list"], list): return response["list"]
        if "subjects" in response and isinstance(response["subjects"], list): return response["subjects"]
        if "searchResults" in response and isinstance(response["searchResults"], list): return response["searchResults"]

        if "results" in response and isinstance(response["results"], list):
            items = []
            for section in response["results"]:
                if "subjects" in section and isinstance(section["subjects"], list):
                    items.extend(section["subjects"])
                elif "list" in section and isinstance(section["list"], list):
                    items.extend(section["list"])
            if items: return items
        return []

    def get_details(self, subject_id):
        path = f"/wefeed-mobile-bff/subject-api/get?subjectId={subject_id}"
        try:
            res = self.get(path)
            return res if res else {}
        except Exception as e:
            xbmc.log(f"Erro ao buscar detalhes: {e}", xbmc.LOGERROR)
            return {}

    def get_all_resources(self, subject_id, season=0, episode=0):
        all_items = []
        page = 1
        per_page = 20
        
        while page <= 5:
            path = f"/wefeed-mobile-bff/subject-api/resource?subjectId={subject_id}"
            if season != 0 or episode != 0:
                path += f"&se={season}&ep={episode}"
            path += f"&page={page}&perPage={per_page}"

            try:
                res = self.get(path)
                items = []
                if isinstance(res, dict):
                    items = res.get("list", res.get("resources", []))
                elif isinstance(res, list):
                    items = res

                if not items:
                    break
                
                all_items.extend(items)
                
                if len(items) < per_page:
                    break
                    
                page += 1
            except Exception:
                break

        return all_items

# ==========================================
# FUNÇÕES AUXILIARES
# ==========================================
api = MovieBoxPlayerAPI()

def build_url(query):
    return PLUGIN_URL + '?' + urllib.parse.urlencode(query)

def extract_qualities(data_dict):
    """Extrai opções de resolução do dicionário do item ou de seus resourceDetectors."""
    qualidades_dict = {}
    if not isinstance(data_dict, dict):
        return qualidades_dict

    resource_detectors = data_dict.get("resourceDetectors", [])
    for detector in resource_detectors:
        resolution_list = detector.get("resolutionList", [])
        for item in resolution_list:
            res_num = item.get("resolution")
            codec = item.get("codecName", "").upper()
            url = item.get("resourceLink") or item.get("downloadUrl")
            if url and res_num:
                label = f"{res_num}P ({codec})" if codec else f"{res_num}P"
                qualidades_dict[label] = url

        if not qualidades_dict and detector.get("downloadUrl"):
            qualidades_dict["Padrão"] = detector.get("downloadUrl")

    if not qualidades_dict and "resolutionList" in data_dict:
        for item in data_dict.get("resolutionList", []):
            res_num = item.get("resolution")
            codec = item.get("codecName", "").upper()
            url = item.get("resourceLink") or item.get("downloadUrl")
            if url and res_num:
                label = f"{res_num}P ({codec})" if codec else f"{res_num}P"
                qualidades_dict[label] = url

    if not qualidades_dict:
        url = data_dict.get("resourceLink") or data_dict.get("downloadUrl") or data_dict.get("url")
        res_num = data_dict.get("resolution")
        codec = str(data_dict.get("codecName") or "").upper()
        if url:
            label = f"{res_num}P ({codec})" if res_num and codec else (f"{res_num}P" if res_num else "Padrão")
            qualidades_dict[label] = url

    return qualidades_dict

# ==========================================
# ROTAS E INTERFACE DO KODI
# ==========================================
def main_menu():
    """Menu principal com mensagem de boas-vindas e histórico de filme/série salvos."""
    
    # === MENSAGEM DE BOAS-VINDAS ===
    welcome = xbmcgui.ListItem(
        label="[COLOR lime]★ Bem-vindo ao MovieBox ★[/COLOR]",
        label2="Assista filmes e séries grátis em alta qualidade"
    )
    
    welcome.setArt({
        'thumb': 'https://movieboxtv.app/wp-content/uploads/2026/04/Movie-Box-icon-MovieBox.webp',
        'icon': 'https://movieboxtv.app/wp-content/uploads/2026/04/Movie-Box-icon-MovieBox.webp',
        'fanart': 'https://editorial.rottentomatoes.com/wp-content/uploads/2019/07/RT_300EssentialMovies_600x314.jpg',
        'poster': 'https://movieboxtv.app/wp-content/uploads/2026/04/Movie-Box-icon-MovieBox.webp'
    })
    
    welcome.setInfo('video', {
        'title': 'Bem-vindo ao MovieBox',
        'plot': 'Assista filmes, séries e animes gratuitamente. Baixe para assistir offline. Interface simples e rápida.',
        'genre': 'Streaming'
    })
    
    xbmcplugin.addDirectoryItem(
        handle=HANDLE,
        url='',
        listitem=welcome,
        isFolder=False
    )

    # === CONTINUAR ASSISTINDO (ÚLTIMO FILME E ÚLTIMA SÉRIE) ===
    last_items = load_last_item()
    
    # 1. Opção para o Último Filme
    movie = last_items.get('movie')
    if isinstance(movie, dict) and movie.get('subject_id'):
        m_title = movie.get('title', 'Filme')
        m_cover = movie.get('cover_url', '')

        url_movie = build_url({
            'action': 'list_resources',
            'subject_id': movie['subject_id'],
            'title': m_title,
            'cover_url': m_cover
        })
        li_movie = xbmcgui.ListItem(f"[COLOR deepskyblue]▶ Continuar Filme: {m_title}[/COLOR]")
        li_movie.setArt({
            'thumb': m_cover or 'https://upload.wikimedia.org/wikipedia/commons/thumb/1/17/Play_icon.svg/1024px-Play_icon.svg.png',
            'icon': m_cover or 'https://themoviebox.xyz/favicon.ico',
            'poster': m_cover
        })
        xbmcplugin.addDirectoryItem(handle=HANDLE, url=url_movie, listitem=li_movie, isFolder=True)

    # 2. Opção para a Última Série
    series = last_items.get('series')
    if isinstance(series, dict) and series.get('subject_id'):
        s_title = series.get('title', 'Série')
        s_cover = series.get('cover_url', '')

        url_series = build_url({
            'action': 'list_resources',
            'subject_id': series['subject_id'],
            'title': s_title,
            'cover_url': s_cover
        })
        li_series = xbmcgui.ListItem(f"[COLOR orange]▶ Continuar Série: {s_title}[/COLOR]")
        li_series.setArt({
            'thumb': s_cover or 'https://upload.wikimedia.org/wikipedia/commons/thumb/1/17/Play_icon.svg/1024px-Play_icon.svg.png',
            'icon': s_cover or 'https://themoviebox.xyz/favicon.ico',
            'poster': s_cover
        })
        xbmcplugin.addDirectoryItem(handle=HANDLE, url=url_series, listitem=li_series, isFolder=True)
    
    # === ITEM DE BUSCA ===
    url = build_url({'action': 'search_dialog'})
    li = xbmcgui.ListItem("[COLOR yellow] Buscar Filmes e Séries[/COLOR]")
    li.setArt({
        'thumb': 'https://upload.wikimedia.org/wikipedia/commons/thumb/7/70/Search_icon.svg/3840px-Search_icon.svg.png',
        'icon': 'https://themoviebox.xyz/favicon.ico'
    })
    xbmcplugin.addDirectoryItem(handle=HANDLE, url=url, listitem=li, isFolder=True)
    
    xbmcplugin.endOfDirectory(HANDLE)

def search_dialog():
    """Teclado virtual do Kodi."""
    keyboard = xbmcgui.Dialog().input("Pesquisar", type=xbmcgui.INPUT_ALPHANUM)
    if keyboard:
        list_search_results(keyboard)

def list_search_results(query):
    """Lista os resultados formatando tags de tipo por cor."""
    try:
        results = api.search(query)
        
        for item in results:
            if not isinstance(item, dict):
                continue

            raw_title = str(item.get("title") or item.get("name") or "Desconhecido")
            subject_id = str(item.get("subjectId") or item.get("id") or "")
            subject_type = int(item.get("subjectType") or 1)
            
            if not subject_id or subject_id == "None":
                continue

            if subject_type == 1:
                display_title = f"[COLOR deepskyblue][Filme][/COLOR] {raw_title}"
            else:
                display_title = f"[COLOR orange][Série][/COLOR] {raw_title}"

            cover_data = item.get("cover")
            cover_url = ""
            if isinstance(cover_data, dict):
                cover_url = str(cover_data.get("url") or "")
            elif isinstance(cover_data, str):
                cover_url = cover_data
            
            li = xbmcgui.ListItem(display_title)
            if cover_url:
                li.setArt({'thumb': cover_url, 'poster': cover_url})
            
            url = build_url({
                'action': 'list_resources', 
                'subject_id': subject_id,
                'title': raw_title,
                'cover_url': cover_url
            })
            
            xbmcplugin.addDirectoryItem(handle=HANDLE, url=url, listitem=li, isFolder=True)
            
    except Exception as e:
        xbmcgui.Dialog().notification("Erro", str(e), xbmcgui.NOTIFICATION_ERROR)

    xbmcplugin.endOfDirectory(HANDLE)

def list_resources(subject_id, title, cover_url=""):
    """Salva o item acessado no slot correto (filme ou série), seleciona idioma e exibe conteúdos."""
    try:
        dialog = xbmcgui.Dialog()

        # 1. Busca detalhes do item principal
        details = api.get_details(subject_id)
        if not details:
            xbmcgui.Dialog().notification("Aviso", "Não foi possível carregar os detalhes.", xbmcgui.NOTIFICATION_WARNING)
            xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
            return

        subject_type = int(details.get("subjectType", 1))

        # Tenta obter a capa via detalhes se não tiver vindo pelo parâmetro
        if not cover_url and details:
            cover_data = details.get("cover")
            if isinstance(cover_data, dict):
                cover_url = str(cover_data.get("url") or "")
            elif isinstance(cover_data, str):
                cover_url = cover_data

        # Salva o filme ou a série no seu devido slot
        save_last_item(subject_id, title, cover_url, subject_type)

        target_subject_id = subject_id

        # 1. SELEÇÃO DE IDIOMA
        dubs = details.get("dubs", [])
        if dubs and len(dubs) > 1:
            lang_names = [d.get("lanName", "Desconhecido") for d in dubs]
            
            idx_lang = dialog.select(f"Idioma - {title}", lang_names)
            if idx_lang < 0:
                xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
                return
            
            selected_dub = dubs[idx_lang]
            dub_subject_id = selected_dub.get("subjectId")
            
            if dub_subject_id and str(dub_subject_id) != str(subject_id):
                target_subject_id = str(dub_subject_id)
                details = api.get_details(target_subject_id)

        # 2. SE FOR FILME (subjectType == 1)
        if subject_type == 1:
            qualidades_dict = extract_qualities(details)
            if not qualidades_dict:
                xbmcgui.Dialog().notification("Aviso", "Nenhum link encontrado.", xbmcgui.NOTIFICATION_WARNING)
                xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
                return

            lista_qualidades = list(qualidades_dict.keys())
            qualidade_escolhida = lista_qualidades[0]
            if len(lista_qualidades) > 1:
                idx_qual = dialog.select(f"Qualidade - {title}", lista_qualidades)
                if idx_qual < 0:
                    xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
                    return
                qualidade_escolhida = lista_qualidades[idx_qual]

            xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
            url_final = qualidades_dict[qualidade_escolhida]
            
            opcao = dialog.select(f"O que deseja fazer? - {title}", ["Assistir", "Baixar"])
            if opcao == 0:
                play_video(url_final, title)
            elif opcao == 1:
                download_video(url_final, title)
            return

        # 3. SE FOR SÉRIE (subjectType == 2)
        episodes = api.get_all_resources(target_subject_id, season=0, episode=0)

        if not episodes:
            xbmcgui.Dialog().notification("Aviso", "Nenhum episódio encontrado.", xbmcgui.NOTIFICATION_WARNING)
            xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
            return

        for idx, ep in enumerate(episodes):
            se_val = ep.get("se") or 1
            ep_val = ep.get("ep") or ep.get("episode") or (idx + 1)
            
            ep_title = ep.get("title") or ep.get("name") or ""
            if ep_title:
                label = f"S{se_val:02d}E{ep_val:02d} - {ep_title}"
            else:
                label = f"S{se_val:02d}E{ep_val:02d}"

            li = xbmcgui.ListItem(label)

            info_tag = li.getVideoInfoTag()
            info_tag.setTitle(label)
            info_tag.setTvShowTitle(title)
            info_tag.setSeason(int(se_val))
            info_tag.setEpisode(int(ep_val))
            
            if ep.get("duration"):
                info_tag.setDuration(int(ep.get("duration")))

            if cover_url:
                li.setArt({'thumb': cover_url, 'poster': cover_url})

            url = build_url({
                'action': 'play_episode',
                'ep_data': json.dumps(ep),
                'title': f"{title} - {label}"
            })

            xbmcplugin.addDirectoryItem(handle=HANDLE, url=url, listitem=li, isFolder=False)

        xbmcplugin.setContent(HANDLE, 'episodes')
        xbmcplugin.endOfDirectory(HANDLE)

    except Exception as e:
        xbmc.log(f"[MovieBox API] Erro em list_resources: {str(e)}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification("Erro", f"Erro: {str(e)}", xbmcgui.NOTIFICATION_ERROR)
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)

def play_episode(ep_data_str, title):
    """Executado ao clicar em um episódio da pasta de episódios."""
    try:
        dialog = xbmcgui.Dialog()
        ep = json.loads(ep_data_str)

        target_dict = ep
        ep_subject_id = ep.get("subjectId") or ep.get("resourceId")
        if ep_subject_id:
            fetched_details = api.get_details(str(ep_subject_id))
            if fetched_details:
                target_dict = fetched_details

        qualidades_dict = extract_qualities(target_dict)

        if not qualidades_dict:
            xbmcgui.Dialog().notification("Aviso", "Nenhum link de reprodução encontrado.", xbmcgui.NOTIFICATION_WARNING)
            return

        lista_qualidades = list(qualidades_dict.keys())

        if len(lista_qualidades) > 1:
            idx_qual = dialog.select(f"Qualidade - {title}", lista_qualidades)
            if idx_qual < 0:
                return
            qualidade_escolhida = lista_qualidades[idx_qual]
        else:
            qualidade_escolhida = lista_qualidades[0]

        url_final = qualidades_dict[qualidade_escolhida]
        
        opcao = dialog.select(f"O que deseja fazer? - {title}", ["Assistir", "Baixar"])
        if opcao == 0:
            play_video(url_final, title)
        elif opcao == 1:
            download_video(url_final, title)

    except Exception as e:
        xbmc.log(f"[MovieBox API] Erro em play_episode: {str(e)}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification("Erro", f"Erro ao tocar episódio: {str(e)}", xbmcgui.NOTIFICATION_ERROR)

def play_video(video_url, title=""):
    """Inicia o Player interno do Kodi."""
    play_item = xbmcgui.ListItem(path=video_url)
    if title:
        play_item.setInfo('video', {'title': title})
    xbmc.Player().play(video_url, play_item)

def download_video(video_url, title):
    import urllib.request
    import os
    
    dialog = xbmcgui.Dialog()
    dest_folder = dialog.browseSingle(3, 'Selecione a pasta para salvar', 'files')
    if not dest_folder:
        return
        
    safe_title = "".join([c for c in title if c.isalnum() or c in (' ', '_', '-')]).strip()
    file_path = os.path.join(dest_folder, f"{safe_title}.mp4")
    
    dp = xbmcgui.DialogProgress()
    dp.create("Baixando Mídia", title)
    
    try:
        req = urllib.request.urlopen(video_url)
        total_size = int(req.info().get('Content-Length', -1))
        downloaded = 0
        chunk_size = 8192
        
        with open(file_path, 'wb') as f:
            while True:
                if dp.iscanceled():
                    break
                chunk = req.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                
                if total_size > 0:
                    percent = int((downloaded / total_size) * 100)
                    dp.update(percent, f"Baixado: {downloaded / (1024 * 1024):.2f} MB")
        
        if not dp.iscanceled():
            dialog.notification("MovieBox", "Download concluído com sucesso!", xbmcgui.NOTIFICATION_INFO)
    except Exception as e:
        xbmc.log(f"[MovieBox API] Erro no download: {e}", xbmc.LOGERROR)
        dialog.notification("Erro", "Falha ao realizar download.", xbmcgui.NOTIFICATION_ERROR)
    finally:
        dp.close()
# ==========================================
# GERENCIADOR DE ROTAS
# ==========================================
def router(paramstring):
    params = dict(urllib.parse.parse_qsl(paramstring))
    action = params.get('action')

    if action is None:
        main_menu()
    elif action == 'search_dialog':
        search_dialog()
    elif action == 'list_resources':
        list_resources(
            params.get('subject_id'), 
            params.get('title'), 
            params.get('cover_url', '')
        )
    elif action == 'play_episode':
        play_episode(params.get('ep_data'), params.get('title'))
    elif action == 'play_video':
        play_video(params.get('video_url'))

if __name__ == '__main__':
    router(sys.argv[2][1:])