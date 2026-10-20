// Translations and small behaviours for about.html. Russian stays in the HTML itself (also the no-JS fallback);
// Kazakh and English replace elements marked with data-i18n (inner HTML) and data-i18n-label (aria-label).
// Every key below mirrors the Russian structure in about.html. All strings are static.
(() => {
  const EOX_MAPS = '<a href="https://maps.eox.at/">EOX::Maps</a>';
  const EOX_LICENSE = "https://cloudless.eox.at/documentation/license";
  const CC_BY_SA = '<a href="https://creativecommons.org/licenses/by-sa/4.0/" target="_blank" rel="noopener noreferrer">CC BY-SA 4.0</a>';

  const T = {
    kk: {
      title: "Серуен — деректер және құпиялылық",
      tagline: "Астанадағы серуенге арналған ЖИ-көмекші",
      back: "Артқа",
      skip: "Негізгі мәтінге өту",
      langLabel: "Тіл",
      pageTitle: "Деректер және құпиялылық",
      intro: "Бұл бетте Серуеннің құрылғыңызда не сақтайтыны, серверге, Gemini-ге және басқа қызметтерге не жіберетіні және ұсыныстардың қалай жасалатыны түсіндіріледі. Төменде дереккөздер мен олардың шектеулері, қауіпсіздік, фото авторлары, сондай-ақ тарихтар, кездесулер және қысқы серуендер туралы айтылады.",
      tocTitle: "Мазмұны",
      toToc: "Мазмұнға оралу",
      dataTitle: "Деректеріңіз және оларды басқару",
      geminiTitle: "Gemini-ге не жіберіледі",
      readTitle: "Ұсыныстар қалай жасалады",
      sourcesTitle: "Дереккөздер және шектеулер",
      safetyTitle: "Қауіпсіздік",
      photosTitle: "Фотосуреттердің авторлары",
      cityTitle: "Тарихтар, кездесулер және қысқы серуендер",
      data: `
          <p class="summary">Аккаунтсыз. Жеке жазбалар мен сақталған серуендер осы браузерде қалады.</p>
          <ul class="bullets">
            <li><b>Құрылғыда.</b> «Менің орындарым» мен жазбалар жойылғанға дейін құрылғыдағы IndexedDB-де сақталады. Оларды «Менің орындарым → Бүкіл тарихты тазалау» арқылы немесе браузер баптауларынан жоюға болады. Ортақ құрылғыда олар оның басқа пайдаланушыларына қолжетімді.</li>
            <li><b>Серверде.</b> Жазбалардың мәтіні серверге де, Gemini-ге де жіберілмейді. Сүзгілеу кезінде сервер таңдалған шектеулерді және алынып тасталған немесе барған орындардың ID-лерін алады. Серверде пайдаланушының тұрақты тарихы жоқ.</li>
            <li><b>Орналасқан жер.</b> Координаттар құрылғыда да, серверде де 3 таңбаға дейін (шамамен 100 м) дөңгелектенеді. Бұл дәлдікті төмендетеді, бірақ <strong class="flag">орналасқан жеріңізді анонимді етпейді</strong>. Геолокациядан бас тартып, картадан қоғамдық бағдарды таңдауға болады.</li>
            <li><b>Сыртқы қызметтер.</b> Іздеу кезінде 2ГИС дөңгелектенген орталықты және іздеу сөздерін алады. Маршрутты құру, қайта есептеу, жаңарту және экспорттау кезінде OSRM дөңгелектенген бастау мен мәре нүктелерін, сондай-ақ аялдамалардың координаттарын алуы мүмкін. Ауа райы Астана орталығы үшін сұралады. Карточкадағы батырма сыртқы навигаторға орынның координаттарын береді.</li>
            <li><b>Журналдар мен трекерлер.</b> Қолданба журналы сұрау мәтіні мен координаттарды жазбайды. Хостингтің, карталардың, қаріптердің және сыртқы API-лердің өз журналдары мен ережелері бар; олар IP-мекенжайды алуы мүмкін. Қолданба жарнамалық трекерлер орнатпайды.</li>
            <li><b>Баптаулар және қойынды.</b> Тақырып пен карта көрінісі тек құрылғыда сақталады. Таңдалған орын мен қайта есептеулерді болдырмау тарихы қойындының жадында тұрады; қойынды жабылғаннан кейін сақталған серуенді ашу немесе жаңасын құру керек.</li>
          </ul>
          <details class="tech">
            <summary>Техникалық мәліметтер: сұраулар мен кэштер</summary>
            <ul>
              <li>Біздің API-ге жіберілетін сұраулар нүктені сұрау денесінде береді.</li>
              <li>Сервер кэштерінің көлемі шектеулі және олар жадта сақталады: қарапайым жауап 30 минутқа дейін, 2ГИС іздеу деректері 5 минутқа дейін, фото талдауы 6 сағатқа дейін қайта қолданылады. Мерзімі өткен жазба ығыстырылғанға немесе сервер қайта іске қосылғанға дейін қалуы мүмкін. Сұрау кілттері хэштеледі.</li>
            </ul>
          </details>`,
      gemini: `
          <p class="summary">Gemini-ге сұрау мәтіні мен үміткер орындар туралы мәліметтер жіберіледі. Жеке жазбалар мен бару тарихы оған жіберілмейді, бірақ сұрауға өзіңіз жазған мәтін ЖИ-ге түсуі мүмкін.</p>
          <div class="split">
            <div class="box sent">
              <h3>Gemini-ге жіберіледі</h3>
              <ul>
                <li>Сұрау мәтіні</li>
                <li>Контекст: тіл, уақыт, топ құрамы, ауа райы</li>
                <li>Шектеулер</li>
                <li>Үміткер орындар туралы мәліметтер</li>
              </ul>
              <p><b>Фотоны талдау үшін</b> орынның суреттері, оның атауы, санаты, сұрау мәтіні және топ құрамы беріледі.</p>
            </div>
            <div class="box kept">
              <h3>Gemini-ге жіберілмейді</h3>
              <ul>
                <li>Геопозицияңыз бен мәреңіздің бөлек өрістері</li>
                <li>Бару тарихы</li>
                <li>Жеке жазбалар</li>
              </ul>
            </div>
          </div>
          <p class="callout">Егер сұрауға мекенжайды немесе атты өзіңіз жазсаңыз, бұл мәтін ЖИ-ге түсуі мүмкін: жеке мәліметтерді автоматты түрде жою жоқ. Іздеуде жеке мәліметтерді көрсетпеңіз.</p>
          <p>Gemini қолжетімсіз болғанда іріктеу ережелер бойынша жүреді және бұл тиісінше белгіленеді.</p>`,
      read: `
          <p class="summary">Код қашықтықтарды, жұмыс кестелерін, шектеулер мен бюджетті тексереді, ал Gemini берілген фактілер бойынша қысқа түсіндірмелер жазады. Мәртебелер мен жаяу жүру уақыты деректер бойынша есептеледі және орнында тексеруді алмастырмайды.</p>
          <ul class="bullets">
            <li><b>Міндеттердің бөлінуі.</b> Код орындарды таңдап, ретке келтіреді, қашықтықтарды, жұмыс кестелерін, шектеулер мен бюджетті тексереді. Gemini берілген фактілер бойынша қысқа түсіндірмелер мен не істеуге болатыны туралы идеялар жазады. Қабылданған мәтін «ЖИ идеясы» деп белгіленеді; қате болса, ережелер бойынша құрылған мәтін көрсетіледі.</li>
            <li><b>Қысқа түсіндірме</b> деректер мен соңғы есептен құралады: сұраумен не сәйкес келді, қанша жүру керек және қайту жолын немесе мәрені қоса алғанда бару қанша уақыт алады. Wi-Fi, розетка немесе тыныштық сұралса, оның расталмағаны тура айтылады. Мекеменің түрі өздігінен ыңғайлылықтарды растамайды.</li>
            <li><b>ЖИ белгілері.</b> «Орынды ЖИ таңдады» белгісі таңдауға қатысты; түсіндірме мәтінін сервер құрастырады. ЖИ мәртебесі орынның сенімділігін бағалау емес.</li>
            <li><b>«Қазір ашық»</b> — дереккөздің 30 күннен ескі емес кестесіне сәйкестік, есікті немесе бос үстелдерді тексеру емес. «Ашық болуы мүмкін» жұмыс уақыты ескірек екенін білдіреді. Болашақ уақыт үшін ағымдағы жағдай белгісіз.</li>
            <li><b>Жаяу жүру уақыты</b> — болжам. Ол мұздың, жабылған жолдардың, баспалдақтардың жоқтығына немесе жолдың арбамен өтуге жарамдылығына кепілдік бермейді.</li>
          </ul>`,
      sources: `
          <p class="summary">Орындар OpenStreetMap пен 2ГИС-тен, сипаттамалардың бір бөлігі Уикипедиядан, фотосуреттер Wikimedia Commons-тан және команданың суреттерінен алынады. Төменде әр дереккөздің не беретіні және оның шектеулері көрсетілген.</p>
          <ul class="bullets">
            <li><b>OpenStreetMap</b> (ODbL) — жергілікті базаның негізі; <b>Уикипедия</b> (CC BY-SA) — сипаттамалардың бір бөлігі. Тегтер бойынша құрастырылған мәтіндер генерацияланған деп белгіленген.</li>
            <li><b>2ГИС</b> — онлайн іздеу, рейтингтер және жұмыс кестелері. Деректер тұрақты базаға импортталмайды. Онлайн іздеу қолжетімсіз болса немесе лайықты орын таппаса, интерфейс жергілікті базаны пайдаланады және дереккөзді белгілейді.</li>
            <li><b>Google Places</b>: рейтингтер мен жұмыс уақытына сұраулар өшірілген.</li>
            <li><b>Фото</b> — Wikimedia Commons және команданың суреттері. Көрсету алдында нақты нысанға байланысы және файлдың бақылау сомасы тексеріледі; координаттардың жақындығы мен ЖИ болжамы фотосуреттің сол орынға тиесілі екенін дәлелдемейді. Тексерілмеген суреттер көрсетілмейді. Авторы мен лицензиясы материалдың жанында көрсетілген.</li>
            <li><b>Фото талдауы.</b> ЖИ тек көрінетінді сипаттайды: жарық, интерьер, отыратын орындар. Фото тыныштықты, қауіпсіздікті, қазір бос үстелдердің барын немесе бүкіл маршруттың қолжетімділігін дәлелдемейді. Талдау қателері болуы мүмкін; талдаудың болмауы орынның нашар екенін білдірмейді.</li>
            <li><b>Ыңғайлылықтар мен шығындар</b> тек жаңа әрі расталған жазба болғанда ескеріледі. Белгісіз баға нөл деп саналмайды; міндетті емес сатып алу тегін мәзірді білдірмейді. Бәйтерекке ақылы көтерілу туралы мәліметтер айналадағы алаңға емес, көтерілуге қатысты.</li>
            <li><b>Карта:</b> OpenStreetMap сызбасы; спутник пен жазулар — ${EOX_MAPS}. 2025 жылғы Sentinel-2 суреттері шолу үшін ғана: олар орынның қазіргі жағдайын көрсетпейді және кіреберістерді немесе өтуге болатынын растамайды. Карта жеткізушісі IP-мекенжайды және көрсетілетін тайлдардың нөмірлерін (карта аймағын) алады.</li>
          </ul>
          <details class="tech">
            <summary>Спутник қабатының лицензиясы және офлайн режим</summary>
            <p>Спутник коммерциялық емес оқу жобасында <a href="${EOX_LICENSE}">EOX шарттары (CC BY-NC-SA)</a> бойынша пайдаланылады; коммерциялық іске қосу үшін бөлек лицензия немесе басқа дереккөз қажет. Спутниктік тайлдар офлайн режим үшін сақталмайды.</p>
          </details>`,
      safety: `
          <p class="summary">Іріктеу тәулік уақытын, топтағы баланы және ауа райын ескеріп, кейбір орындарды алып тастайды. Бұл — деректер сүзгілері, қауіпсіздік кепілі емес: жағдай мен кері жолды өзіңіз бағалаңыз.</p>
          <ul class="rules">
            <li><span class="rule-fig" aria-hidden="true">1 км</span><p><b>Түнде (22:00–06:00)</b> радиус 1 км-мен шектеледі; жарықтандыру немесе адам көптігі туралы белгісі жоқ ашық аспан астындағы орындар алынып тасталады. Бұл белгілер де ескіруі мүмкін. Бұл — деректер сүзгісі, қауіпсіздік кепілі емес.</p></li>
            <li><span class="rule-fig" aria-hidden="true">18+</span><p><b>Баламен барғанда</b> барлар, кальянханалар және 18+ орындар алынып тасталады.</p></li>
            <li><span class="rule-fig" aria-hidden="true">500 м</span><p><b>−15 °C-тан бастап аязда немесе 10 м/с-тан бастап желде</b> радиус 500 м-мен шектеледі және жабық орындарға басымдық беріледі.</p></li>
          </ul>
          <p class="callout"><b>Мұз және жабық аумақтар.</b> Су айдындарының мұзына шығуға немесе жабық аумақтарға кіруге кеңес бермейміз. Шығар алдында нақты жағдайды және кері жолды бағалаңыз.</p>`,
      photosIntro: "Фотосуреттер Wikimedia Commons-тан еркін лицензиялармен (CC0, CC BY, CC BY-SA) алынып, сайт үшін кішірейтілген. Авторлары:",
      city: `
          <p class="summary">Бұл бөлімде орындар туралы тарихтардың, кездесулердің және қысқы режимнің қалай жұмыс істейтіні және олардың нені тексермейтіні айтылады.</p>
          <h3>Тарихтар</h3>
          <ul class="bullets">
            <li>Тарихтар нақты нысандарға қатысты: әрқайсысының дереккөзі және Уикипедия батырмасы бар.</li>
            <li>Мәтіндер қысқартылып, аударылған; Уикипедия мазмұндамалары ${CC_BY_SA} шарттарымен қолжетімді. Авторлар мен түзетулер тарихын бастапқы мақаладан табуға болады.</li>
            <li>Жинақ ойдан шығарылған әңгімелер есебінен емес, тексеруден кейін толықтырылады.</li>
          </ul>
          <h3>Кездесулер</h3>
          <ul class="bullets">
            <li>Кездесу үшін қатысушылардың келісімімен қоғамдық бағдарларды таңдаңыз.</li>
            <li>Екі нүкте де дөңгелектеніп, серверге жіберіледі; 2ГИС олардың арасындағы іздеу орталығын алуы мүмкін. Кездесу нүктелері профильде немесе сілтемеде сақталмайды.</li>
            <li>Уақыттар бір болжамды модель бойынша салыстырылады, кері жол қосылмаған. Пунктир сызықтар өткелдердің барын немесе көшелердің қолжетімділігін растамайды.</li>
          </ul>
          <h3>Қысқы режим</h3>
          <ul class="bullets">
            <li>Қысқы режим жекелеген жаяу бөліктердің уақытын шектейді және ғимарат ішіндегі аялдамаларды іріктейді.</li>
            <li>Ол мұзды, ғимараттар арасындағы желді немесе дәл қазір ішке кіруге болатынын тексермейді.</li>
            <li>Алдын ала көрініс есептелген кезеңдерді көрсетеді: бұл панорама да, нақты жағдайды бақылау да емес.</li>
          </ul>`,
    },
    en: {
      title: "Seruen — data & privacy",
      tagline: "AI walking assistant for Astana",
      back: "Back",
      skip: "Skip to main content",
      langLabel: "Language",
      pageTitle: "Data and privacy",
      intro: "This page explains what Seruen keeps on your device, what it sends to our server, Gemini and other services, and how recommendations are made. Further down: sources and their limits, safety, photo credits, and stories, meetups and winter walks.",
      tocTitle: "Contents",
      toToc: "Back to contents",
      dataTitle: "Your data and controls",
      geminiTitle: "What goes to Gemini",
      readTitle: "How recommendations work",
      sourcesTitle: "Sources and limitations",
      safetyTitle: "Safety",
      photosTitle: "Photo credits",
      cityTitle: "Stories, meetups and winter walks",
      data: `
          <p class="summary">No account. Personal notes and saved walks stay in this browser.</p>
          <ul class="bullets">
            <li><b>On your device.</b> “My places” and notes are stored in IndexedDB on your device until deleted. You can delete them in “My places → Clear all history” or in your browser settings. On a shared device they are available to its other users.</li>
            <li><b>On the server.</b> Note text is not sent to the server or to Gemini. When filtering, the server receives the selected constraints and the IDs of excluded or visited places. There is no permanent user history on the server.</li>
            <li><b>Location.</b> Coordinates are rounded to 3 decimal places (about 100 m) on the device and on the server. This reduces precision but <strong class="flag">does not make your location anonymous</strong>. You can decline geolocation and pick a public landmark on the map instead.</li>
            <li><b>External services.</b> When you search, 2GIS receives the rounded centre and the search words. When a route is built, recalculated, refreshed or exported, OSRM may receive the rounded start and finish, as well as the coordinates of the stops. Weather is requested for the centre of Astana. The button on a place card passes the place’s coordinates to an external navigation app.</li>
            <li><b>Logs and trackers.</b> The app log does not record request text or coordinates. Hosting, maps, fonts and external APIs have their own logs and policies; they may receive your IP address. The app does not install advertising trackers.</li>
            <li><b>Settings and the open tab.</b> The theme and map view are saved only on your device. The selected place and the undo history of recalculations live in the tab’s memory; after closing the tab, open a saved walk or build a new one.</li>
          </ul>
          <details class="tech">
            <summary>Technical details: requests and caches</summary>
            <ul>
              <li>Requests to our API send the point in the request body.</li>
              <li>Server caches are size-limited and kept in memory: a regular response is reused for up to 30 minutes, 2GIS search data for up to 5 minutes, photo analysis for up to 6 hours. An expired entry may remain until it is evicted or the server restarts. Request keys are hashed.</li>
            </ul>
          </details>`,
      gemini: `
          <p class="summary">Gemini receives the request text and information about candidate places. Personal notes and visit history are not sent there, but anything you type into the request yourself may reach the AI.</p>
          <div class="split">
            <div class="box sent">
              <h3>Sent to Gemini</h3>
              <ul>
                <li>The request text</li>
                <li>Context: language, time, who is in the group, weather</li>
                <li>Constraints</li>
                <li>Information about candidate places</li>
              </ul>
              <p><b>For photo analysis</b>, the place’s photos, its name, category, the request text and the group makeup are sent.</p>
            </div>
            <div class="box kept">
              <h3>Not sent to Gemini</h3>
              <ul>
                <li>Separate fields with your location and finish point</li>
                <li>Your visit history</li>
                <li>Personal notes</li>
              </ul>
            </div>
          </div>
          <p class="callout">If you type an address or a name into the request yourself, that text may reach the AI: personal information is not removed automatically. Do not put personal information into searches.</p>
          <p>When Gemini is unavailable, places are chosen by rules and marked accordingly.</p>`,
      read: `
          <p class="summary">Code checks distances, opening hours, constraints and budget; Gemini writes short explanations from the facts it is given. Statuses and walking times are calculated from data and do not replace checking on site.</p>
          <ul class="bullets">
            <li><b>Who does what.</b> Code selects and orders places and checks distances, opening hours, constraints and budget. Gemini writes short explanations and activity ideas from the facts it is given. Accepted text is labelled “AI idea”; if something goes wrong, rule-based text is shown.</li>
            <li><b>The short explanation</b> is built from the data and the final calculation: what matched your request, how far you walk and how long the visit takes including the way back or to the finish. If you ask for Wi-Fi, power outlets or quiet and this is not confirmed, the explanation says so directly. The type of venue alone does not confirm amenities.</li>
            <li><b>AI labels.</b> The “AI selected the place” label refers to the choice; the explanation text is assembled by the server. AI status is not a rating of how reliable a place is.</li>
            <li><b>“Open now”</b> means the source’s schedule, no older than 30 days, matches the time — not a check of the door or of free tables. “Probably open” means the hours are older. For a future time, the current situation is unknown.</li>
            <li><b>Walking time</b> is an estimate. It does not guarantee there is no ice, closure or stairs, or that the path is accessible with a stroller.</li>
          </ul>`,
      sources: `
          <p class="summary">Places come from OpenStreetMap and 2GIS, some descriptions from Wikipedia, and photos from Wikimedia Commons and the team’s own shots. Below is what each source provides and where its limits are.</p>
          <ul class="bullets">
            <li><b>OpenStreetMap</b> (ODbL) is the basis of the local database; <b>Wikipedia</b> (CC BY-SA) supplies some of the descriptions. Texts composed from tags are marked as generated.</li>
            <li><b>2GIS</b> provides online search, ratings and opening hours. Its data is not imported into a permanent database. If online search is unavailable or finds no suitable places, the interface uses the local database and shows the source.</li>
            <li><b>Google Places</b>: rating and opening-hours requests are turned off.</li>
            <li><b>Photos</b> come from Wikimedia Commons and the team’s own shots. Before display, the link to a specific place and the file checksum are verified; nearby coordinates or an AI guess do not prove that a photo shows the place. Unverified photos are not shown. The author and licence are given with each item.</li>
            <li><b>Photo analysis.</b> The AI describes only what is visible: light, interior, seating. A photo does not prove quiet, safety, free tables right now or accessibility of the whole route. Analysis errors are possible; a missing analysis does not mean the place is bad.</li>
            <li><b>Amenities and costs</b> are taken into account only when there is a fresh, confirmed record. An unknown price is not treated as zero; an optional purchase does not mean a free menu. Information about the paid ascent of Baiterek refers to the ascent, not to the square around it.</li>
            <li><b>Map:</b> OpenStreetMap base map; satellite and labels — ${EOX_MAPS}. The 2025 Sentinel-2 imagery is an overview only: it does not show the current state of a place and does not confirm entrances or whether you can get through. The map provider receives your IP address and the numbers of the tiles shown (the map area).</li>
          </ul>
          <details class="tech">
            <summary>Satellite layer licence and offline use</summary>
            <p>The satellite layer is used in a non-commercial educational project under the <a href="${EOX_LICENSE}">EOX terms (CC BY-NC-SA)</a>; a commercial launch needs a separate licence or another source. Satellite tiles are not saved for offline use.</p>
          </details>`,
      safety: `
          <p class="summary">Recommendations take the time of day, a child in the group and the weather into account and exclude some places. These are data filters, not a safety guarantee: check the conditions and your way back yourself.</p>
          <ul class="rules">
            <li><span class="rule-fig" aria-hidden="true">1 km</span><p><b>At night (22:00–06:00)</b> the radius is limited to 1 km; outdoor places without marks for lighting or people around are excluded. These marks can also be out of date. This is a data filter, not a safety guarantee.</p></li>
            <li><span class="rule-fig" aria-hidden="true">18+</span><p><b>With a child</b>, bars, hookah lounges and 18+ places are excluded.</p></li>
            <li><span class="rule-fig" aria-hidden="true">500 m</span><p><b>In frost from −15 °C or wind from 10 m/s</b>, the radius is limited to 500 m and indoor places get priority.</p></li>
          </ul>
          <p class="callout"><b>Ice and closed areas.</b> We do not recommend walking on the ice of rivers and lakes or entering closed areas. Check the actual conditions and your way back before you go.</p>`,
      photosIntro: "Photos are taken from Wikimedia Commons under free licences (CC0, CC BY, CC BY-SA) and downsized for the site. Authors:",
      city: `
          <p class="summary">How place stories, meetups and winter mode work, and what they do not check.</p>
          <h3>Stories</h3>
          <ul class="bullets">
            <li>Stories relate to specific places: each has a source and a Wikipedia button.</li>
            <li>The texts are shortened and translated; Wikipedia retellings are available under ${CC_BY_SA}. Authors and edit history can be found in the original article.</li>
            <li>The collection grows after review, not through made-up stories.</li>
          </ul>
          <h3>Meetups</h3>
          <ul class="bullets">
            <li>For a meetup, choose public landmarks with everyone’s consent.</li>
            <li>Both points are rounded and sent to the server; 2GIS may receive the search centre between them. Meeting points are not saved in a profile or a link.</li>
            <li>Times are compared using the same estimation model; the way back is not included. Dashed lines do not confirm that crossings exist or that streets are accessible.</li>
          </ul>
          <h3>Winter mode</h3>
          <ul class="bullets">
            <li>Winter mode limits the length of individual outdoor walking legs and picks indoor stops.</li>
            <li>It does not check ice, wind between buildings or whether you can get in right now.</li>
            <li>The preview shows calculated stages: it is not a panorama or an observation of real conditions.</li>
          </ul>`,
    },
  };

  const LANGS = ["kk", "ru", "en"];
  const nodes = Array.from(document.querySelectorAll("[data-i18n]"));
  const ruText = new Map(nodes.map((el) => [el, el.innerHTML])); // Russian originals from the HTML
  const labelled = Array.from(document.querySelectorAll("[data-i18n-label]"));
  const ruLabel = new Map(labelled.map((el) => [el, el.getAttribute("aria-label")]));
  const ruOnly = document.querySelectorAll("[data-ru-only]");

  function readStored() {
    try { return JSON.parse(localStorage.getItem("seruen_lang")); } catch { return null; }
  }

  function apply(lang) {
    document.documentElement.lang = lang;
    nodes.forEach((el) => {
      const key = el.dataset.i18n;
      el.innerHTML = lang === "ru" ? ruText.get(el) : T[lang][key] ?? ruText.get(el);
    });
    labelled.forEach((el) => {
      el.setAttribute("aria-label", lang === "ru" ? ruLabel.get(el) : T[lang][el.dataset.i18nLabel] ?? ruLabel.get(el));
    });
    // The short English summary (and its contents entry) is only useful next to the Russian text.
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

  // Anchors land below the sticky header: CSS reads its real height (it wraps on narrow screens).
  const head = document.querySelector(".top");
  const setHead = () => document.documentElement.style.setProperty("--head-h", `${head.offsetHeight}px`);
  setHead();
  if ("ResizeObserver" in window) new ResizeObserver(setHead).observe(head);

  // The contents list marks the section being read.
  const tocLinks = Array.from(document.querySelectorAll('.toc a[href^="#"]'));
  const sections = tocLinks.map((a) => document.getElementById(a.hash.slice(1)));
  function spy() {
    const line = head.offsetHeight + window.innerHeight * 0.25;
    let current = -1;
    sections.forEach((s, i) => { if (s && !s.hidden && s.getBoundingClientRect().top <= line) current = i; });
    const root = document.documentElement;
    if (window.innerHeight + window.scrollY >= root.scrollHeight - 4) { // at the very end: the last visible section
      sections.forEach((s, i) => { if (s && !s.hidden) current = i; });
    }
    tocLinks.forEach((a, i) => {
      if (i === current) a.setAttribute("aria-current", "location"); else a.removeAttribute("aria-current");
    });
  }
  let queued = false;
  window.addEventListener("scroll", () => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => { queued = false; spy(); });
  }, {passive: true});
  window.addEventListener("resize", spy);
  spy();
  // Smooth scrolling only once the page has settled, so a deep link (about.html#photos) jumps there directly.
  const glide = () => requestAnimationFrame(() => document.documentElement.classList.add("glide"));
  if (document.readyState === "complete") glide(); else window.addEventListener("load", glide, {once: true});

  document.querySelectorAll(".lang button").forEach((b) => b.addEventListener("click", () => {
    lang = b.dataset.lang;
    try { localStorage.setItem("seruen_lang", JSON.stringify(lang)); } catch { /* private mode */ }
    if (fromUrl) { // drop ?lang so a reload keeps the new choice
      const url = new URL(location.href);
      url.searchParams.delete("lang");
      history.replaceState(null, "", url);
    }
    apply(lang);
    spy();
  }));
})();
