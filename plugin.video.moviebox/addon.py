import sys
import os
import json
import urllib.request
import urllib.parse
import urllib.error
import xbmcgui
import xbmcplugin
import xbmcaddon
import xbmcvfs
import ssl
import xbmc

# Configurações do Kodi[cite: 2]
ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')
PLUGIN_URL = sys.argv[0]
HANDLE = int(sys.argv[1])

# Configuração de persistência (salvar último filme e série separadamente)[cite: 2]
PROFILE_PATH = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
LAST_ITEM_FILE = os.path.join(PROFILE_PATH, 'last_item.json')

def save_last_item(subject_id, detail_path, title, cover_url="", subject_type=1):
    """Salva o último filme ou série acessado, agora incluindo o detailPath."""
    try:
        if not os.path.exists(PROFILE_PATH):
            os.makedirs(PROFILE_PATH)

        data = load_last_item()
        if not isinstance(data, dict):
            data = {}

        item_data = {
            'subject_id': str(subject_id),
            'detail_path': str(detail_path),
            'title': str(title),
            'cover_url': str(cover_url)
        }

        # Separa o armazenamento entre Filme (1) e Série (2)[cite: 2]
        if int(subject_type) == 1:
            data['movie'] = item_data
        else:
            data['series'] = item_data

        with open(LAST_ITEM_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception as e:
        xbmc.log(f"[MovieBox API] Erro ao salvar último item: {e}", xbmc.LOGERROR)

def load_last_item():
    """Carrega as informações salvas do filme e da série[cite: 2]."""
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
# CLASSE DA API MOVIEBOX (ATUALIZADA)
# ==========================================
class MovieBoxPlayerAPI:
    def __init__(self):
        self.base_api_url = "https://h5-api.aoneroom.com"
        self.base_play_url = "https://movie-box.co"
        self.bearer_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1aWQiOjQ3ODUyMjcxMzcxNjA4MzIyNTYsImF0cCI6MywiZXh0IjoiMTc4ODA0MDE5NCIsImV4cCI6MTc5NTgxNjE5NCwiaWF0IjoxNzg4MDM5ODk0fQ.1ep5atx1--OYCCVjy9107CyEnSgBRjtn3z83i43OnCo" #[cite: 1]
        self.user_agent = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"

    def _build_headers(self, referer=None, auth=False):
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if referer:
            headers["Referer"] = referer
        if auth:
            headers['Authorization'] =f"Bearer {self.bearer_token}"
        return headers

    def request(self, method, url, body_str=None, referer=None, auth=False):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        headers = self._build_headers(referer, auth)
        req = urllib.request.Request(url, headers=headers, method=method)
        
        if body_str:
            req.data = body_str.encode('utf-8')

        try:
            with urllib.request.urlopen(req, timeout=10, context=ctx) as response:
                response_data = response.read().decode('utf-8')
                json_data = json.loads(response_data)
                
                return json_data.get("data", json_data)
        except urllib.error.HTTPError as e:
            erro_body = e.read().decode('utf-8') if e.fp else "Sem corpo"
            xbmc.log(f"[MovieBox API] HTTPError {e.code} na URL {url}: {erro_body}", xbmc.LOGERROR)
        except Exception as e:
            xbmc.log(f"[MovieBox API] Erro na requisição: {str(e)}", xbmc.LOGERROR)
            
        return {}

    def get(self, url, referer=None, auth=False):
        return self.request("GET", url, referer=referer, auth=auth)

    def post(self, url, payload, referer=None, auth=False):
        body_str = json.dumps(payload, separators=(',', ':'))
        return self.request("POST", url, body_str, referer=referer, auth=auth)

    def search(self, query, page=1, referer="https://movieboxph.org/", auth=True):
        url = f"{self.base_api_url}/wefeed-h5api-bff/subject/search"
        payload = {
            "page": int(page),
            "perPage": 24,
            "keyword": query,
            "subjectType": 0
        }
        res = self.post(url, payload, referer, auth=auth)
        
        if not res: return [], False
        
        # Lê o objeto pager do JSON para descobrir se há uma próxima página
        has_more = res.get("pager", {}).get("hasMore", False)
        
        # Mapeia as possíveis chaves que contêm os resultados
        items = []
        if "items" in res and isinstance(res["items"], list): items = res["items"]
        elif "list" in res and isinstance(res["list"], list): items = res["list"]
        elif "subjects" in res and isinstance(res["subjects"], list): items = res["subjects"]
        elif "searchResults" in res and isinstance(res["searchResults"], list): items = res["searchResults"]
        
        # Retorna os itens E o status da paginação
        return items, has_more

    def get_details(self, detail_path, auth=True):
        url = f"{self.base_api_url}/wefeed-h5api-bff/detail?detailPath={urllib.parse.quote(detail_path)}" #[cite: 1]
        return self.get(url, referer="https://movieboxph.org", auth=auth) #[cite: 1]

    def get_play_info(self, subject_id, detail_path, season=0, episode=0):
        url = f"{self.base_play_url}/wefeed-h5api-bff/subject/play?subjectId={subject_id}&se={season}&ep={episode}&detailPath={urllib.parse.quote(detail_path)}&streamSignType=1&supportCodecs%5Bh264%5D=1" #[cite: 1]
        ref = f"https://movie-box.co/movies/{urllib.parse.quote(detail_path)}?id=${subject_id}&type=/movie/detail&detailSe=&detailEp=&lang=ptbr" #[cite: 1]
        
        return self.get(url, referer=ref)
    
# ==========================================
# FUNÇÕES AUXILIARES
# ==========================================
api = MovieBoxPlayerAPI()

def build_url(query):
    return PLUGIN_URL + '?' + urllib.parse.urlencode(query) #[cite: 2]

def extract_qualities(data_dict):
    """Extrai opções de resolução do dicionário do item."""
    qualidades_dict = {}
    if not isinstance(data_dict, dict):
        return qualidades_dict

    # 1. Nova estrutura: procura nas listas "streams", "dash" e "hls"
    for stream_type in ["streams", "dash", "hls"]:
        for item in data_dict.get(stream_type, []):
            res_num = str(item.get("resolutions", ""))
            codec = item.get("codecName", "").upper()
            url = item.get("url")
            
            if url and res_num:
                # O DASH pode retornar resoluções combinadas (ex: "720,480"). Pega a primeira.
                main_res = res_num.split(',')[0]
                label = f"{main_res}P ({codec})" if codec else f"{main_res}P"
                
                # Opcional: Adicionar a tag DASH para não sobrescrever o MP4 da mesma resolução
                if stream_type.upper() == "DASH":
                    label += " [DASH]"
                
                qualidades_dict[label] = url

    # Se já encontrou os links na nova estrutura, retorna.
    if qualidades_dict:
        return qualidades_dict

    # 2. Estrutura antiga: resourceDetectors
    resource_detectors = data_dict.get("resourceDetectors", [])
    for detector in resource_detectors:
        resolution_list = detector.get("resolutionList", [])
        for item in resolution_list:
            res_num = item.get("resolution") or item.get("resolutions")
            codec = item.get("codecName", "").upper()
            url = item.get("resourceLink") or item.get("downloadUrl") or item.get("url")
            if url and res_num:
                label = f"{res_num}P ({codec})" if codec else f"{res_num}P"
                qualidades_dict[label] = url

        if not qualidades_dict and detector.get("downloadUrl"):
            qualidades_dict["Padrão"] = detector.get("downloadUrl")

    # 3. Estrutura antiga: resolutionList direta
    if not qualidades_dict and "resolutionList" in data_dict:
        for item in data_dict.get("resolutionList", []):
            res_num = item.get("resolution") or item.get("resolutions")
            codec = item.get("codecName", "").upper()
            url = item.get("resourceLink") or item.get("downloadUrl") or item.get("url")
            if url and res_num:
                label = f"{res_num}P ({codec})" if codec else f"{res_num}P"
                qualidades_dict[label] = url

    # 4. Fallback genérico
    if not qualidades_dict:
        url = data_dict.get("resourceLink") or data_dict.get("downloadUrl") or data_dict.get("url")
        res_num = data_dict.get("resolution") or data_dict.get("resolutions")
        codec = str(data_dict.get("codecName") or "").upper()
        if url:
            label = f"{res_num}P ({codec})" if res_num and codec else (f"{res_num}P" if res_num else "Padrão")
            qualidades_dict[label] = url

    return qualidades_dict

# ==========================================
# ROTAS E INTERFACE DO KODI
# ==========================================
def main_menu():
    """Menu principal com mensagem de boas-vindas e histórico de filme/série salvos[cite: 2]."""
    
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
    
    xbmcplugin.addDirectoryItem(handle=HANDLE, url='', listitem=welcome, isFolder=False)

    last_items = load_last_item()
    
    # Último Filme
    movie = last_items.get('movie')
    if isinstance(movie, dict) and movie.get('detail_path'):
        m_title = movie.get('title', 'Filme')
        m_cover = movie.get('cover_url', '')
        m_back = movie.get('back_url', '')

        url_movie = build_url({
            'action': 'list_resources',
            'subject_id': movie.get('subject_id', ''),
            'detail_path': movie['detail_path'],
            'title': m_title,
            'cover_url': m_cover,
            'back_url': m_back
        })
        li_movie = xbmcgui.ListItem(f"[COLOR deepskyblue]▶ Continuar Filme: {m_title}[/COLOR]")
        li_movie.setArt({'thumb': m_cover or 'https://upload.wikimedia.org/wikipedia/commons/thumb/1/17/Play_icon.svg/1024px-Play_icon.svg.png', 
                         'fanart': m_back or ''})
        xbmcplugin.addDirectoryItem(handle=HANDLE, url=url_movie, listitem=li_movie, isFolder=True)

    # Última Série
    series = last_items.get('series')
    if isinstance(series, dict) and series.get('detail_path'):
        s_title = series.get('title', 'Série')
        s_cover = series.get('cover_url', '')

        url_series = build_url({
            'action': 'list_resources',
            'subject_id': series.get('subject_id', ''),
            'detail_path': series['detail_path'],
            'title': s_title,
            'cover_url': s_cover
        })
        li_series = xbmcgui.ListItem(f"[COLOR orange]▶ Continuar Série: {s_title}[/COLOR]")
        li_series.setArt({'thumb': s_cover or 'https://upload.wikimedia.org/wikipedia/commons/thumb/1/17/Play_icon.svg/1024px-Play_icon.svg.png'})
        xbmcplugin.addDirectoryItem(handle=HANDLE, url=url_series, listitem=li_series, isFolder=True)
    
    # Buscar
    url = build_url({'action': 'search_dialog'})
    li = xbmcgui.ListItem("[COLOR yellow] Buscar Filmes e Séries[/COLOR]")
    li.setArt({'thumb': 'https://upload.wikimedia.org/wikipedia/commons/thumb/7/70/Search_icon.svg/3840px-Search_icon.svg.png'})
    xbmcplugin.addDirectoryItem(handle=HANDLE, url=url, listitem=li, isFolder=True)
    
    xbmcplugin.endOfDirectory(HANDLE)

def search_dialog():
    keyboard = xbmcgui.Dialog().input("Pesquisar", type=xbmcgui.INPUT_ALPHANUM)
    if keyboard:
        list_search_results(keyboard, page=1)

def list_search_results(query, page=1):
    try:
        page = int(page)
        # Recebe os resultados e a confirmação de próxima página
        results, has_more = api.search(query, page)
        
        for item in results:
            if not isinstance(item, dict):
                continue

            raw_title = str(item.get("title") or item.get("name") or "Desconhecido")
            subject_id = str(item.get("subjectId") or item.get("id") or "")
            detail_path = str(item.get("detailPath") or "")
            subject_type = int(item.get("subjectType") or 1)
            
            has_resource = item.get("hasResource", True)
            is_playable = bool(detail_path and has_resource)

            tipo_str = "[COLOR deepskyblue][Filme][/COLOR]" if subject_type == 1 else "[COLOR orange][Série][/COLOR]"
            
            if not is_playable:
                display_title = f"{tipo_str} {raw_title} [COLOR red](Indisponível)[/COLOR]"
            else:
                display_title = f"{tipo_str} {raw_title}"

            cover_data = item.get("cover")
            cover_url = cover_data.get("url") if isinstance(cover_data, dict) else (cover_data if isinstance(cover_data, str) else "")

            back_data = item.get('stills')
            back_url = back_data.get('url') if isinstance(back_data, dict) else (back_data if isinstance(back_data, str) else "")
            
            li = xbmcgui.ListItem(display_title)
            art_dict = {}
            if cover_url:
                art_dict['thumb'] = cover_url
                art_dict['poster'] = cover_url
                art_dict['icon'] = cover_url
            if back_url:
                art_dict['fanart'] = back_url

            if art_dict:
                li.setArt(art_dict)
            
            if is_playable:
                url = build_url({
                    'action': 'list_resources', 
                    'subject_id': subject_id,
                    'detail_path': detail_path,
                    'title': raw_title,
                    'cover_url': cover_url,
                    'back_url': back_url
                })
                xbmcplugin.addDirectoryItem(handle=HANDLE, url=url, listitem=li, isFolder=True)
            else:
                url = build_url({
                    'action': 'unplayable_warning', 
                    'title': raw_title
                })
                xbmcplugin.addDirectoryItem(handle=HANDLE, url=url, listitem=li, isFolder=False)

        # ==========================================
        # BOTÕES DE PAGINAÇÃO
        # ==========================================
        if page > 1:
            li_prev = xbmcgui.ListItem("[COLOR yellow]⏪ Voltar Página[/COLOR]")
            url_prev = build_url({'action': 'search_page', 'query': query, 'page': page - 1})
            xbmcplugin.addDirectoryItem(handle=HANDLE, url=url_prev, listitem=li_prev, isFolder=True)

        if has_more:
            li_next = xbmcgui.ListItem("[COLOR yellow]⏩ Próxima Página[/COLOR]")
            url_next = build_url({'action': 'search_page', 'query': query, 'page': page + 1})
            xbmcplugin.addDirectoryItem(handle=HANDLE, url=url_next, listitem=li_next, isFolder=True)
            
    except Exception as e:
        xbmcgui.Dialog().notification("Erro", str(e), xbmcgui.NOTIFICATION_ERROR)

    xbmcplugin.endOfDirectory(HANDLE)
    
def list_resources(subject_id, detail_path, title, cover_url=""):
    try:
        dialog = xbmcgui.Dialog()

        # Busca dados completos na raiz do JSON para acessar 'subject' e 'resource'
        full_data = api.get_details(detail_path)
        details = full_data.get('subject') if isinstance(full_data, dict) else None
        
        if not details:
            xbmcgui.Dialog().notification("Aviso", "Não foi possível carregar os detalhes.", xbmcgui.NOTIFICATION_WARNING)
            xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
            return

        subject_type = int(details.get("subjectType", 1))

        if not cover_url:
            cover_data = details.get("cover")
            cover_url = cover_data.get("url") if isinstance(cover_data, dict) else (cover_data if isinstance(cover_data, str) else "")

        # Salva o filme ou a série com o detailPath
        save_last_item(subject_id, detail_path, title, cover_url, subject_type)

        # 1. SELEÇÃO DE IDIOMA
        dubs = details.get("dubs", [])
        if dubs and len(dubs) > 1:
            lang_names = [d.get("lanName", "Desconhecido") for d in dubs]
            idx_lang = dialog.select(f"Idioma - {title}", lang_names)
            if idx_lang < 0:
                xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
                return
            
            selected_dub = dubs[idx_lang]
            detail_path = selected_dub.get("detailPath", detail_path)
            subject_id = selected_dub.get("subjectId", subject_id)
            
            # Recarrega os dados completos com o novo detailPath de idioma
            full_data = api.get_details(detail_path)
            details = full_data.get('subject') if isinstance(full_data, dict) else None

        # 2. SE FOR FILME (subjectType == 1)
        if subject_type == 1:
            play_data = api.get_play_info(subject_id, detail_path, season=0, episode=0)
            qualidades_dict = extract_qualities(play_data)
            
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
            
            plot = details.get("description") or details.get("postTitle") or ""
            fanart = details.get("stills", {}).get("url", "") if isinstance(details.get("stills"), dict) else ""
            
            opcao = dialog.select(f"O que deseja fazer? - {title}", ["Assistir", "Baixar"])
            if opcao == 0:
                play_video(url_final, title=title, plot=plot, cover_url=cover_url, fanart=fanart)
            elif opcao == 1:
                download_video(url_final, title)
            return

        # 3. SE FOR SÉRIE (subjectType == 2)
        # Extrai a nova estrutura resource > seasons
        seasons_data = full_data.get("resource", {}).get("seasons", [])
        
        # Estrutura antiga mantida como fallback
        episodes_legacy = details.get("episodeList", details.get("episodes", details.get("resources", [])))

        if not seasons_data and not episodes_legacy:
            xbmcgui.Dialog().notification("Aviso", "Nenhum episódio encontrado.", xbmcgui.NOTIFICATION_WARNING)
            xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
            return

        # Popula o Kodi usando a nova estrutura (maxEp)
        if seasons_data:
            for season in seasons_data:
                se_val = season.get("se", 1)
                max_ep = season.get("maxEp", 1)
                
                # Cria a listagem de episódios dinamicamente daquele 1 até maxEp
                for ep_val in range(1, max_ep + 1):
                    label = f"S{se_val:02d}E{ep_val:02d}"
                    li = xbmcgui.ListItem(label)
                    
                    info_tag = li.getVideoInfoTag()
                    info_tag.setTitle(label)
                    info_tag.setTvShowTitle(title)
                    info_tag.setSeason(int(se_val))
                    info_tag.setEpisode(int(ep_val))
                    
                    if cover_url:
                        li.setArt({'thumb': cover_url, 'poster': cover_url})

                    url = build_url({
                        'action': 'play_episode',
                        'subject_id': subject_id,
                        'detail_path': detail_path,
                        'se': se_val,
                        'ep': ep_val,
                        'title': f"{title} - {label}"
                    })
                    xbmcplugin.addDirectoryItem(handle=HANDLE, url=url, listitem=li, isFolder=False)
                    
        # Popula usando a estrutura legada
        else:
            for idx, ep in enumerate(episodes_legacy):
                se_val = ep.get("se") or 1
                ep_val = ep.get("ep") or ep.get("episode") or (idx + 1)
                ep_title = ep.get("title") or ep.get("name") or ""
                label = f"S{se_val:02d}E{ep_val:02d} - {ep_title}" if ep_title else f"S{se_val:02d}E{ep_val:02d}"

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
                    'subject_id': subject_id,
                    'detail_path': detail_path,
                    'se': se_val,
                    'ep': ep_val,
                    'title': f"{title} - {label}"
                })
                xbmcplugin.addDirectoryItem(handle=HANDLE, url=url, listitem=li, isFolder=False)

        xbmcplugin.setContent(HANDLE, 'episodes')
        xbmcplugin.endOfDirectory(HANDLE)

    except Exception as e:
        xbmc.log(f"[MovieBox API] Erro em list_resources: {str(e)}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification("Erro", f"Erro: {str(e)}", xbmcgui.NOTIFICATION_ERROR)
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
        
def play_episode(subject_id, detail_path, se, ep, title):
    """Executado ao clicar em um episódio chamando a nova rota get_play_info."""
    try:
        dialog = xbmcgui.Dialog()
        
        # Puxa os links de vídeo
        play_data = api.get_play_info(subject_id, detail_path, season=se, episode=ep)
        qualidades_dict = extract_qualities(play_data)

        if not qualidades_dict:
            xbmcgui.Dialog().notification("Aviso", "Nenhum link de reprodução encontrado.", xbmcgui.NOTIFICATION_WARNING)
            return

        lista_qualidades = list(qualidades_dict.keys())
        qualidade_escolhida = lista_qualidades[0]
        
        if len(lista_qualidades) > 1:
            idx_qual = dialog.select(f"Qualidade - {title}", lista_qualidades)
            if idx_qual < 0:
                return
            qualidade_escolhida = lista_qualidades[idx_qual]

        url_final = qualidades_dict[qualidade_escolhida]
        
        # Puxa detalhes básicos para preencher o player
        details = api.get_details(detail_path)['subject']
        plot = details.get("description") or details.get("postTitle") or ""
        cover_data = details.get("cover")
        cover_url = cover_data.get("url") if isinstance(cover_data, dict) else (cover_data if isinstance(cover_data, str) else "")
        fanart = details.get("stills", {}).get("url", "") if isinstance(details.get("stills"), dict) else ""
        
        opcao = dialog.select(f"O que deseja fazer? - {title}", ["Assistir", "Baixar"])
        if opcao == 0:
            play_video(url_final, title=title, plot=plot, cover_url=cover_url, fanart=fanart)
        elif opcao == 1:
            download_video(url_final, title)

    except Exception as e:
        xbmc.log(f"[MovieBox API] Erro em play_episode: {str(e)}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification("Erro", f"Erro ao tocar episódio: {str(e)}", xbmcgui.NOTIFICATION_ERROR)

def play_video(video_url, title="", plot="", cover_url="", fanart="", referer="https://movieboxph.org/"):
    import urllib.parse
    
    if referer:
        headers = f"|Referer={urllib.parse.quote(referer)}&User-Agent={urllib.parse.quote(api.user_agent)}"
        video_url += headers

    play_item = xbmcgui.ListItem(path=video_url)
    
    # Previne o "Não disponível" caso a API entregue o campo em branco
    if not plot or plot.strip() == "":
        plot = "Sinopse não informada pelo servidor."
        
    info_dict = {
        'title': title,
        'plot': plot,
        'mediatype': 'video'
    }
    
    # Método legado (Kodi 19 Matrix ou inferior)
    play_item.setInfo('video', info_dict)
    
    # Método novo (Kodi 20+ Nexus/Omega)
    if hasattr(play_item, 'getVideoInfoTag'):
        info_tag = play_item.getVideoInfoTag()
        info_tag.setTitle(title)
        info_tag.setPlot(plot)
        info_tag.setMediaType('video')
    
    # Injeta as imagens (Capa e Fundo)
    art_dict = {}
    if cover_url:
        art_dict['thumb'] = cover_url
        art_dict['poster'] = cover_url
        art_dict['icon'] = cover_url
    if fanart:
        art_dict['fanart'] = fanart
        
    if art_dict:
        play_item.setArt(art_dict)
        
    xbmc.Player().play(video_url, play_item)

def download_video(video_url, title, referer="https://movieboxph.org/"):
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
        # Cria a requisição estruturada para aceitar cabeçalhos HTTP
        headers = {'User-Agent': api.user_agent}
        if referer:
            headers['Referer'] = referer
            
        req = urllib.request.Request(video_url, headers=headers)
        response = urllib.request.urlopen(req)
        
        total_size = int(response.info().get('Content-Length', -1))
        downloaded = 0
        chunk_size = 8192
        
        with open(file_path, 'wb') as f:
            while True:
                if dp.iscanceled():
                    break
                chunk = response.read(chunk_size)
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
    elif action == 'search_page':
        # Rota que captura a ação de avançar/voltar página
        list_search_results(params.get('query'), int(params.get('page', 1)))
    elif action == 'list_resources':
        list_resources(
            params.get('subject_id'), 
            params.get('detail_path'),
            params.get('title'), 
            params.get('cover_url', ''),
            params.get('back_url', '')
        )
    elif action == 'play_episode':
        play_episode(
            params.get('subject_id'),
            params.get('detail_path'),
            int(params.get('se', 0)),
            int(params.get('ep', 0)),
            params.get('title')
        )
    elif action == 'play_video':
        play_video(params.get('video_url'))
    elif action == 'unplayable_warning':
        xbmcgui.Dialog().notification("Aviso", "O servidor ainda não disponibilizou vídeos para este título.", xbmcgui.NOTIFICATION_WARNING)

if __name__ == '__main__':
    router(sys.argv[2][1:])