// Translations for about.html. Russian stays in the HTML itself (also the no-JS fallback);
// Kazakh and English replace elements marked with data-i18n. All strings are static.
(() => {
  const EOX_MAPS = '<a href="https://maps.eox.at/">EOX::Maps</a>';
  const EOX_LICENSE = "https://cloudless.eox.at/documentation/license";
  const CC_BY_SA = '<a href="https://creativecommons.org/licenses/by-sa/4.0/" target="_blank" rel="noopener noreferrer">CC BY-SA 4.0</a>';

  const T = {
    kk: {
      title: "Серуен — деректер және құпиялылық",
      tagline: "Деректер және құпиялылық",
      back: "← Артқа",
      data: `
      <h2>Деректеріңіз және оларды басқару</h2>
      <p class="lead">Аккаунтсыз. Жеке жазбалар мен сақталған серуендер осы браузерде қалады.</p>
      <ul>
        <li>«Менің орындарым» мен жазбалар жойылғанға дейін құрылғыдағы IndexedDB-де сақталады. Оларды «Менің орындарым → Бүкіл тарихты тазалау» арқылы немесе браузер баптауларынан жоюға болады. Ортақ құрылғыда олар оның басқа пайдаланушыларына қолжетімді.</li>
        <li>Жазбалардың мәтіні серверге де, Gemini-ге де жіберілмейді. Сүзгілеу кезінде сервер таңдалған шектеулерді және алынып тасталған немесе барған орындардың ID-лерін алады. Серверде пайдаланушының тұрақты тарихы жоқ.</li>
        <li>Координаттар құрылғыда да, серверде де 3 таңбаға дейін (шамамен 100 м) дөңгелектенеді. Бұл дәлдікті төмендетеді, бірақ <b>орналасқан жеріңізді анонимді етпейді</b>. Геолокациядан бас тартып, картадан қоғамдық бағдарды таңдауға болады.</li>
        <li>Біздің API-ге жіберілетін сұраулар нүктені сұрау денесінде береді. Іздеу кезінде 2ГИС дөңгелектенген орталықты және іздеу сөздерін алады. Маршрутты құру, қайта есептеу, жаңарту және экспорттау кезінде OSRM дөңгелектенген бастау мен мәре нүктелерін, сондай-ақ аялдамалардың координаттарын алуы мүмкін.</li>
        <li>Ауа райы Астана орталығы үшін сұралады. Карточкадағы батырма сыртқы навигаторға орынның координаттарын береді.</li>
        <li>Сервер кэштерінің көлемі шектеулі және олар жадта сақталады: қарапайым жауап 30 минутқа дейін, 2ГИС іздеу деректері 5 минутқа дейін, фото талдауы 6 сағатқа дейін қайта қолданылады. Мерзімі өткен жазба ығыстырылғанға немесе сервер қайта іске қосылғанға дейін қалуы мүмкін. Сұрау кілттері хэштеледі.</li>
        <li>Қолданба журналы сұрау мәтіні мен координаттарды жазбайды. Хостингтің, карталардың, қаріптердің және сыртқы API-лердің өз журналдары мен ережелері бар; олар IP-мекенжайды алуы мүмкін. Қолданба жарнамалық трекерлер орнатпайды.</li>
      </ul>`,
      gemini: `
      <h2>Gemini-ге не жіберіледі</h2>
      <p>Сұрау мәтіні, контекст (тіл, уақыт, топ құрамы, ауа райы), шектеулер және үміткер орындар туралы мәліметтер. Геопозицияңыз бен мәреңіздің жеке өрістері, бару тарихы және жеке жазбалар Gemini-ге жіберілмейді. Егер сұрауға мекенжайды немесе атты өзіңіз жазсаңыз, бұл мәтін ЖИ-ге түсуі мүмкін: жеке мәліметтерді автоматты түрде жою жоқ.</p>
      <p>Фотоны талдау үшін орынның суреттері, оның атауы, санаты, сұрау мәтіні және топ құрамы беріледі. Іздеуде жеке мәліметтерді көрсетпеңіз. Gemini қолжетімсіз болғанда іріктеу ережелер бойынша жүреді және бұл тиісінше белгіленеді.</p>`,
      read: `
      <h2>Ұсыныстарды қалай түсінуге болады</h2>
      <ul>
        <li>Код орындарды таңдап, ретке келтіреді, қашықтықтарды, жұмыс кестелерін, шектеулер мен бюджетті тексереді. Gemini берілген фактілер бойынша қысқа түсіндірмелер мен не істеуге болатыны туралы идеялар жазады. Қабылданған мәтін «ЖИ идеясы» деп белгіленеді; қате болса, ережелер бойынша құрылған мәтін көрсетіледі.</li>
        <li>Қысқа түсіндірме деректер мен соңғы есептен құралады: сұраумен не сәйкес келді, қанша жүру керек және қайту жолын немесе мәрені қоса алғанда бару қанша уақыт алады. Wi-Fi, розетка немесе тыныштық сұралса, оның расталмағаны тура айтылады.</li>
        <li>Мекеменің түрі өздігінен ыңғайлылықтарды растамайды. «Орынды ЖИ таңдады» белгісі таңдауға қатысты; түсіндірме мәтінін сервер құрастырады. ЖИ мәртебесі орынның сенімділігін бағалау емес.</li>
        <li>«Қазір ашық» — дереккөздің 30 күннен ескі емес кестесіне сәйкестік, есікті немесе бос үстелдерді тексеру емес. «Ашық болуы мүмкін» жұмыс уақыты ескірек екенін білдіреді. Болашақ уақыт үшін ағымдағы жағдай белгісіз.</li>
        <li>Жаяу жүру уақыты — болжам. Ол мұздың, жабылған жолдардың, баспалдақтардың жоқтығына немесе жолдың арбамен өтуге жарамдылығына кепілдік бермейді.</li>
      </ul>`,
      sources: `
      <h2>Дереккөздер және шектеулер</h2>
      <ul>
        <li><b>OpenStreetMap</b> (ODbL) — жергілікті базаның негізі; <b>Уикипедия</b> (CC BY-SA) — сипаттамалардың бір бөлігі. Тегтер бойынша құрастырылған мәтіндер генерацияланған деп белгіленген.</li>
        <li><b>2ГИС</b> — онлайн іздеу, рейтингтер және жұмыс кестелері. Деректер тұрақты базаға импортталмайды. Онлайн іздеу қолжетімсіз болса немесе лайықты орын таппаса, интерфейс жергілікті базаны пайдаланады және дереккөзді белгілейді.</li>
        <li><b>Фото</b> — Wikimedia Commons және команданың суреттері. Көрсету алдында нақты нысанға байланысы және файлдың бақылау сомасы тексеріледі; координаттардың жақындығы мен ЖИ болжамы фотосуреттің сол орынға тиесілі екенін дәлелдемейді. Тексерілмеген суреттер көрсетілмейді. Авторы мен лицензиясы материалдың жанында көрсетілген. «Атмосфера бойынша» іріктеу көрінетін белгілердің тексерілген таңбалауын пайдаланады және Gemini-сіз де жұмыс істей алады.</li>
        <li>ЖИ тек көрінетінді сипаттайды: жарық, интерьер, отыратын орындар. Фото тыныштықты, қауіпсіздікті, қазір бос үстелдердің барын немесе бүкіл маршруттың қолжетімділігін дәлелдемейді. Талдау қателері болуы мүмкін; талдаудың болмауы орынның нашар екенін білдірмейді.</li>
        <li><b>Ыңғайлылықтар мен шығындар</b> тек жаңа әрі расталған жазба болғанда ескеріледі. Белгісіз баға нөл деп саналмайды; міндетті емес сатып алу тегін мәзірді білдірмейді. Бәйтерекке ақылы көтерілу туралы мәліметтер айналадағы алаңға емес, көтерілуге қатысты.</li>
        <li><b>Карта:</b> OpenStreetMap сызбасы; спутник пен жазулар — ${EOX_MAPS}. 2025 жылғы Sentinel-2 суреттері шолу үшін ғана: олар орынның қазіргі жағдайын көрсетпейді және кіреберістерді немесе өтуге болатынын растамайды. Спутник коммерциялық емес оқу жобасында <a href="${EOX_LICENSE}">EOX шарттары (CC BY-NC-SA)</a> бойынша пайдаланылады; коммерциялық іске қосу үшін бөлек лицензия немесе басқа дереккөз қажет. Карта жеткізушісі IP-мекенжайды және көрсетілетін тайлдардың нөмірлерін (карта аймағын) алады. Спутниктік тайлдар офлайн режим үшін сақталмайды.</li>
        <li>Тақырып пен карта көрінісі тек құрылғыда сақталады. Таңдалған орын мен қайта есептеулерді болдырмау тарихы қойындының жадында тұрады; қойынды жабылғаннан кейін сақталған серуенді ашу немесе жаңасын құру керек.</li>
        <li><b>Google Places</b>: рейтингтер мен жұмыс уақытына сұраулар өшірілген.</li>
      </ul>`,
      safety: `
      <h2>Қауіпсіздік</h2>
      <ul>
        <li>Түнде (22:00–06:00) радиус 1 км-мен шектеледі; жарықтандыру немесе адам көптігі туралы белгісі жоқ ашық аспан астындағы орындар алынып тасталады. Бұл белгілер де ескіруі мүмкін. Бұл — деректер сүзгісі, қауіпсіздік кепілі емес.</li>
        <li>Баламен барғанда барлар, кальянханалар және 18+ орындар алынып тасталады. −15 °C-тан бастап аязда немесе 10 м/с-тан бастап желде радиус 500 м-мен шектеледі және жабық орындарға басымдық беріледі.</li>
        <li>Су айдындарының мұзына шығуға немесе жабық аумақтарға кіруге кеңес бермейміз. Шығар алдында нақты жағдайды және кері жолды бағалаңыз.</li>
      </ul>`,
      photosTitle: "Фотосуреттер",
      photosIntro: "Фотосуреттер Wikimedia Commons-тан еркін лицензиялармен (CC0, CC BY, CC BY-SA) алынып, сайт үшін кішірейтілген. Авторлары:",
      city: `
      <h2>Тарихтар, кездесулер және қысқы серуендер</h2>
      <p>Тарихтар нақты нысандарға қатысты: әрқайсысының дереккөзі және Уикипедия батырмасы бар. Мәтіндер қысқартылып, аударылған; Уикипедия мазмұндамалары ${CC_BY_SA} шарттарымен қолжетімді. Авторлар мен түзетулер тарихын бастапқы мақаладан табуға болады. Жинақ ойдан шығарылған әңгімелер есебінен емес, тексеруден кейін толықтырылады.</p>
      <p>Кездесу үшін қатысушылардың келісімімен қоғамдық бағдарларды таңдаңыз. Екі нүкте де дөңгелектеніп, серверге жіберіледі; 2ГИС олардың арасындағы іздеу орталығын алуы мүмкін. Кездесу нүктелері профильде немесе сілтемеде сақталмайды. Уақыттар бір болжамды модель бойынша салыстырылады, кері жол қосылмаған. Пунктир сызықтар өткелдердің барын немесе көшелердің қолжетімділігін растамайды.</p>
      <p>Қысқы режим жекелеген жаяу бөліктердің уақытын шектейді және ғимарат ішіндегі аялдамаларды іріктейді. Ол мұзды, ғимараттар арасындағы желді немесе дәл қазір ішке кіруге болатынын тексермейді. Алдын ала көрініс есептелген кезеңдерді көрсетеді: бұл панорама да, нақты жағдайды бақылау да емес.</p>`,
    },
    en: {
      title: "Seruen — data & privacy",
      tagline: "Data & privacy",
      back: "← Back",
      data: `
      <h2>Your data and how to control it</h2>
      <p class="lead">No account. Personal notes and saved walks stay in this browser.</p>
      <ul>
        <li>“My places” and notes are stored in IndexedDB on your device until deleted. You can delete them in “My places → Clear all history” or in your browser settings. On a shared device they are available to its other users.</li>
        <li>Note text is not sent to the server or to Gemini. When filtering, the server receives the selected constraints and the IDs of excluded or visited places. There is no permanent user history on the server.</li>
        <li>Coordinates are rounded to 3 decimal places (about 100 m) on the device and on the server. This reduces precision but <b>does not make your location anonymous</b>. You can decline geolocation and pick a public landmark on the map instead.</li>
        <li>Requests to our API send the point in the request body. When you search, 2GIS receives the rounded centre and the search words. When a route is built, recalculated, refreshed or exported, OSRM may receive the rounded start and finish, as well as the coordinates of the stops.</li>
        <li>Weather is requested for the centre of Astana. The button on a place card passes the place’s coordinates to an external navigation app.</li>
        <li>Server caches are size-limited and kept in memory: a regular response is reused for up to 30 minutes, 2GIS search data for up to 5 minutes, photo analysis for up to 6 hours. An expired entry may remain until it is evicted or the server restarts. Request keys are hashed.</li>
        <li>The app log does not record request text or coordinates. Hosting, maps, fonts and external APIs have their own logs and policies; they may receive your IP address. The app does not install advertising trackers.</li>
      </ul>`,
      gemini: `
      <h2>What goes to Gemini</h2>
      <p>The request text, context (language, time, who is in the group, weather), constraints and information about candidate places. Separate fields with your location and finish point, your visit history and personal notes are not sent to Gemini. If you type an address or a name into the request yourself, that text may reach the AI: personal information is not removed automatically.</p>
      <p>For photo analysis, the place’s photos, its name, category, the request text and the group makeup are sent. Do not put personal information into searches. When Gemini is unavailable, places are chosen by rules and marked accordingly.</p>`,
      read: `
      <h2>How to read recommendations</h2>
      <ul>
        <li>Code selects and orders places and checks distances, opening hours, constraints and budget. Gemini writes short explanations and activity ideas from the facts it is given. Accepted text is labelled “AI idea”; if something goes wrong, rule-based text is shown.</li>
        <li>The short explanation is built from the data and the final calculation: what matched your request, how far you walk and how long the visit takes including the way back or to the finish. If you ask for Wi-Fi, power outlets or quiet and this is not confirmed, the explanation says so directly.</li>
        <li>The type of venue alone does not confirm amenities. The “AI selected the place” label refers to the choice; the explanation text is assembled by the server. AI status is not a rating of how reliable a place is.</li>
        <li>“Open now” means the source’s schedule, no older than 30 days, matches the time — not a check of the door or of free tables. “Probably open” means the hours are older. For a future time, the current situation is unknown.</li>
        <li>Walking time is an estimate. It does not guarantee there is no ice, closure or stairs, or that the path is accessible with a stroller.</li>
      </ul>`,
      sources: `
      <h2>Sources and limitations</h2>
      <ul>
        <li><b>OpenStreetMap</b> (ODbL) is the basis of the local database; <b>Wikipedia</b> (CC BY-SA) supplies some of the descriptions. Texts composed from tags are marked as generated.</li>
        <li><b>2GIS</b> provides online search, ratings and opening hours. Its data is not imported into a permanent database. If online search is unavailable or finds no suitable places, the interface uses the local database and shows the source.</li>
        <li><b>Photos</b> come from Wikimedia Commons and the team’s own shots. Before display, the link to a specific place and the file checksum are verified; nearby coordinates or an AI guess do not prove that a photo shows the place. Unverified photos are not shown. The author and licence are given with each item. “By atmosphere” matching uses verified labels of visible features and can work without Gemini.</li>
        <li>The AI describes only what is visible: light, interior, seating. A photo does not prove quiet, safety, free tables right now or accessibility of the whole route. Analysis errors are possible; a missing analysis does not mean the place is bad.</li>
        <li><b>Amenities and costs</b> are taken into account only when there is a fresh, confirmed record. An unknown price is not treated as zero; an optional purchase does not mean a free menu. Information about the paid ascent of Baiterek refers to the ascent, not to the square around it.</li>
        <li><b>Map:</b> OpenStreetMap base map; satellite and labels — ${EOX_MAPS}. The 2025 Sentinel-2 imagery is an overview only: it does not show the current state of a place and does not confirm entrances or whether you can get through. The satellite layer is used in a non-commercial educational project under the <a href="${EOX_LICENSE}">EOX terms (CC BY-NC-SA)</a>; a commercial launch needs a separate licence or another source. The map provider receives your IP address and the numbers of the tiles shown (the map area). Satellite tiles are not saved for offline use.</li>
        <li>The theme and map view are saved only on your device. The selected place and the undo history of recalculations live in the tab’s memory; after closing the tab, open a saved walk or build a new one.</li>
        <li><b>Google Places</b>: rating and opening-hours requests are turned off.</li>
      </ul>`,
      safety: `
      <h2>Safety</h2>
      <ul>
        <li>At night (22:00–06:00) the radius is limited to 1 km; outdoor places without marks for lighting or people around are excluded. These marks can also be out of date. This is a data filter, not a safety guarantee.</li>
        <li>With a child, bars, hookah lounges and 18+ places are excluded. In frost from −15 °C or wind from 10 m/s, the radius is limited to 500 m and indoor places get priority.</li>
        <li>We do not recommend walking on the ice of rivers and lakes or entering closed areas. Check the actual conditions and your way back before you go.</li>
      </ul>`,
      photosTitle: "Photos",
      photosIntro: "Photos are taken from Wikimedia Commons under free licences (CC0, CC BY, CC BY-SA) and downsized for the site. Authors:",
      city: `
      <h2>Stories, meetups and winter walks</h2>
      <p>Stories relate to specific places: each has a source and a Wikipedia button. The texts are shortened and translated; Wikipedia retellings are available under ${CC_BY_SA}. Authors and edit history can be found in the original article. The collection grows after review, not through made-up stories.</p>
      <p>For a meetup, choose public landmarks with everyone’s consent. Both points are rounded and sent to the server; 2GIS may receive the search centre between them. Meeting points are not saved in a profile or a link. Times are compared using the same estimation model; the way back is not included. Dashed lines do not confirm that crossings exist or that streets are accessible.</p>
      <p>Winter mode limits the length of individual outdoor walking legs and picks indoor stops. It does not check ice, wind between buildings or whether you can get in right now. The preview shows calculated stages: it is not a panorama or an observation of real conditions.</p>`,
    },
  };

  const LANGS = ["kk", "ru", "en"];
  const nodes = Array.from(document.querySelectorAll("[data-i18n]"));
  const ruText = new Map(nodes.map((el) => [el, el.innerHTML])); // Russian originals from the HTML
  const ruOnly = document.querySelectorAll("[data-ru-only]");

  function readStored() {
    try { return JSON.parse(localStorage.getItem("seruen_lang")); } catch { return null; }
  }

  function apply(lang) {
    document.documentElement.lang = lang;
    nodes.forEach((el) => {
      const key = el.dataset.i18n;
      el.innerHTML = lang === "ru" ? ruText.get(el) : T[lang][key];
    });
    // The short English summary is only useful next to the Russian text.
    ruOnly.forEach((el) => { el.hidden = lang !== "ru"; });
    document.querySelectorAll(".lang button").forEach((b) => {
      const on = b.dataset.lang === lang;
      b.classList.toggle("on", on);
      b.setAttribute("aria-pressed", String(on));
    });
  }

  const fromUrl = new URLSearchParams(location.search).get("lang");
  const stored = readStored();
  let lang = LANGS.includes(fromUrl) ? fromUrl : LANGS.includes(stored) ? stored : "ru";
  apply(lang);

  document.querySelectorAll(".lang button").forEach((b) => b.addEventListener("click", () => {
    lang = b.dataset.lang;
    try { localStorage.setItem("seruen_lang", JSON.stringify(lang)); } catch { /* private mode */ }
    if (fromUrl) { // drop ?lang so a reload keeps the new choice
      const url = new URL(location.href);
      url.searchParams.delete("lang");
      history.replaceState(null, "", url);
    }
    apply(lang);
  }));
})();
