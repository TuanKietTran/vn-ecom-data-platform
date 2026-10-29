package vn.hunt

import android.app.Application
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import java.net.URLEncoder
import java.text.NumberFormat
import java.util.Locale
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.serialization.encodeToString

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            val colors =
                if (androidx.compose.foundation.isSystemInDarkTheme())
                    darkColorScheme(
                        primary = Color(0xFF9BB9FF),
                        onPrimary = Color(0xFF102B68),
                        primaryContainer = Color(0xFF244FA8),
                        onPrimaryContainer = Color(0xFFDCE6FF),
                        secondary = Color(0xFFBFC9DB),
                        onSecondary = Color(0xFF293548),
                        secondaryContainer = Color(0xFF39465D),
                        onSecondaryContainer = Color(0xFFE1E8F2),
                        tertiary = Color(0xFF9BB9FF),
                        onTertiary = Color(0xFF102B68),
                        tertiaryContainer = Color(0xFF244FA8),
                        onTertiaryContainer = Color(0xFFDCE6FF),
                        background = Color(0xFF111827),
                        onBackground = Color(0xFFF3F6FC),
                        surface = Color(0xFF111827),
                        onSurface = Color(0xFFF3F6FC),
                        surfaceVariant = Color(0xFF42506A),
                        onSurfaceVariant = Color(0xFFBBC7DB),
                        outline = Color(0xFF8B98AE),
                        surfaceContainer = Color(0xFF1B2433),
                        surfaceContainerHigh = Color(0xFF243047),
                        surfaceContainerHighest = Color(0xFF2E3A52),
                        surfaceContainerLow = Color(0xFF161E2B),
                        surfaceContainerLowest = Color(0xFF0C121C),
                    )
                else
                    lightColorScheme(
                        primary = Color(0xFF245BDB),
                        onPrimary = Color.White,
                        primaryContainer = Color(0xFFDCE6FF),
                        onPrimaryContainer = Color(0xFF102B68),
                        secondary = Color(0xFF4A5568),
                        onSecondary = Color.White,
                        secondaryContainer = Color(0xFFE1E8F2),
                        onSecondaryContainer = Color(0xFF172033),
                        tertiary = Color(0xFF245BDB),
                        onTertiary = Color.White,
                        tertiaryContainer = Color(0xFFDCE6FF),
                        onTertiaryContainer = Color(0xFF102B68),
                        background = Color(0xFFFFFFFF),
                        onBackground = Color(0xFF172033),
                        surface = Color(0xFFFFFFFF),
                        onSurface = Color(0xFF172033),
                        surfaceVariant = Color(0xFFEAF0FA),
                        onSurfaceVariant = Color(0xFF42506A),
                        outline = Color(0xFF68758D),
                        surfaceContainer = Color(0xFFE7EDF7),
                        surfaceContainerHigh = Color(0xFFDEE6F2),
                        surfaceContainerHighest = Color(0xFFD4DDEC),
                        surfaceContainerLow = Color(0xFFF5F7FB),
                        surfaceContainerLowest = Color.White,
                    )
            MaterialTheme(colorScheme = colors) { HuntClientApp() }
        }
    }
}

fun money(amount: Long?): String =
    amount?.let {
        NumberFormat.getIntegerInstance(Locale.forLanguageTag("vi-VN")).format(it) + " ₫"
    } ?: "Not yet known"

fun observedTime(raw: String): String =
    runCatching {
            java.time.OffsetDateTime.parse(raw)
                .atZoneSameInstant(java.time.ZoneId.systemDefault())
                .format(
                    java.time.format.DateTimeFormatter.ofLocalizedDateTime(
                        java.time.format.FormatStyle.SHORT
                    )
                )
        }
        .getOrDefault(raw)

class HuntModel(app: Application) : AndroidViewModel(app) {
    private val preferences = app.getSharedPreferences("hunt", 0)
    var base by mutableStateOf(preferences.getString("gateway", "http://10.0.2.2:3202")!!)
        private set

    var status by mutableStateOf<Status?>(null)
        private set

    var deals by mutableStateOf<DealResults?>(null)
        private set

    var upcoming by mutableStateOf<UpcomingResults?>(null)
        private set

    var watchedUpcoming by mutableStateOf(
        runCatching { wireJson.decodeFromString<List<UpcomingDeal>>(preferences.getString("watched_upcoming", "[]")!!) }.getOrDefault(emptyList())
    )
        private set

    var loadingUpcoming by mutableStateOf(false)
        private set

    var products by mutableStateOf<List<Product>>(emptyList())
        private set

    var saved by
        mutableStateOf<List<Deal>>(
            runCatching {
                    wireJson.decodeFromString<List<Deal>>(preferences.getString("saved", "[]")!!)
                }
                .getOrDefault(emptyList())
        )
        private set

    var messages by mutableStateOf<List<Turn>>(emptyList())
        private set

    var hunting by mutableStateOf(false)
        private set

    var discovering by mutableStateOf(false)
        private set

    var chatting by mutableStateOf(false)
        private set

    var error by mutableStateOf<String?>(null)
        private set

    private var chatJob: Job? = null

    init {
        refresh()
    }

    fun updateGateway(value: String) {
        base = value.trim().trimEnd('/')
        preferences.edit().putString("gateway", base).apply()
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            try {
                status = wireJson.decodeFromString(Api(base).request("status"))
            } catch (e: Exception) {
                if (e is CancellationException) throw e
                status = null
                error = "Cannot reach the platform. Check Connection settings."
            }
        }
    }

    fun dismiss() {
        error = null
    }

    fun hunt(request: HuntRequest) {
        viewModelScope.launch {
            hunting = true
            error = null
            try {
                deals =
                    wireJson.decodeFromString(
                        Api(base).request("deals", wireJson.encodeToString(request))
                    )
            } catch (e: Exception) {
                if (e is CancellationException) throw e
                error = e.message ?: "Search failed"
            } finally {
                hunting = false
            }
        }
    }

    fun loadUpcoming(includeSynthetic: Boolean) {
        viewModelScope.launch {
            loadingUpcoming = true
            error = null
            try {
                upcoming = wireJson.decodeFromString(
                    Api(base).request("upcoming?include_synthetic=$includeSynthetic")
                )
            } catch (e: Exception) {
                if (e is CancellationException) throw e
                error = e.message ?: "Could not load supplied voucher windows"
            } finally { loadingUpcoming = false }
        }
    }

    fun toggleUpcoming(deal: UpcomingDeal) {
        watchedUpcoming = if (watchedUpcoming.any { it.id == deal.id }) watchedUpcoming.filterNot { it.id == deal.id }
            else (listOf(deal) + watchedUpcoming).take(100)
        preferences.edit().putString("watched_upcoming", wireJson.encodeToString(watchedUpcoming)).apply()
    }

    fun discover(query: String, demo: Boolean) {
        viewModelScope.launch {
            discovering = true
            error = null
            try {
                products =
                    wireJson
                        .decodeFromString<Products>(
                            Api(base)
                                .request(
                                    "products?query=" +
                                        URLEncoder.encode(query, "UTF-8") +
                                        "&include_synthetic=" +
                                        demo
                                )
                        )
                        .products
            } catch (e: Exception) {
                if (e is CancellationException) throw e
                error = e.message ?: "Search failed"
            } finally {
                discovering = false
            }
        }
    }

    fun toggle(deal: Deal) {
        saved =
            if (saved.any { it.offer.id == deal.offer.id })
                saved.filter { it.offer.id != deal.offer.id }
            else (listOf(deal) + saved).take(50)
        preferences.edit().putString("saved", wireJson.encodeToString(saved)).apply()
    }

    fun newChat() {
        if (!chatting) messages = emptyList()
    }

    fun stop() {
        chatJob?.cancel()
        chatting = false
        error = "Response stopped."
    }

    fun send(text: String, model: Boolean) {
        if (chatting || text.isBlank()) return
        val history = messages.takeLast(20).map { it.copy(content = it.content.take(8000)) }
        messages = messages + Turn("user", text)
        chatJob =
            viewModelScope.launch {
                chatting = true
                error = null
                try {
                    val reply =
                        wireJson.decodeFromString<Reply>(
                            Api(base)
                                .request(
                                    "chat?mode=" + (if (model) "model" else "data"),
                                    wireJson.encodeToString(ChatRequest(text, history)),
                                )
                        )
                    messages = messages + Turn("assistant", reply.answer)
                } catch (e: Exception) {
                    if (e is CancellationException) throw e
                    error = e.message ?: "Message failed"
                } finally {
                    chatting = false
                }
            }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HuntClientApp(model: HuntModel = viewModel()) {
    var tab by remember { mutableIntStateOf(0) }
    LaunchedEffect(Unit) { model.loadUpcoming(includeSynthetic = false) }
    var settings by remember { mutableStateOf(false) }
    var address by remember { mutableStateOf(model.base) }
    val labels = listOf("Home", "Hunt", "Discover", "Saved")
    val icons =
        listOf(
            Icons.Outlined.LocalActivity,
            Icons.Outlined.LocalActivity,
            Icons.Outlined.Search,
            Icons.Outlined.FavoriteBorder,
        )
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(if (tab == 0) "Hunt" else labels[tab]) },
                actions = {
                    IconButton(
                        onClick = {
                            address = model.base
                            settings = true
                        }
                    ) {
                        Icon(Icons.Outlined.Settings, "Connection settings")
                    }
                },
            )
        },
        bottomBar = {
            NavigationBar {
                labels.forEachIndexed { i, title ->
                    NavigationBarItem(
                        selected = tab == i,
                        onClick = { tab = i },
                        icon = { if (i == 0) Text("h", style = MaterialTheme.typography.titleMedium, fontWeight = androidx.compose.ui.text.font.FontWeight.Bold) else Icon(icons[i], null) },
                        label = { Text(title) },
                    )
                }
            }
        },
    ) { padding ->
        Column(Modifier.padding(padding).fillMaxSize()) {
            if (model.error != null)
                Surface(color = MaterialTheme.colorScheme.errorContainer) {
                    Row(Modifier.fillMaxWidth().padding(12.dp)) {
                        Text(
                            model.error!!,
                            Modifier.weight(1f),
                            style = MaterialTheme.typography.bodySmall,
                        )
                        TextButton(onClick = model::dismiss) { Text("Dismiss") }
                    }
                }
            when (tab) {
                0 -> ChatScreen(model) { tab = 1 }
                1 -> HuntScreen(model)
                2 -> DiscoverScreen(model)
                else ->
                    LazyColumn(
                        contentPadding = PaddingValues(16.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        item {
                            Text(
                                "Saved snapshots. Recheck current price and voucher availability. Upcoming watchlist stays on this device; no notifications are sent.",
                                style = MaterialTheme.typography.bodySmall,
                            )
                        }
                        if (model.saved.isEmpty() && model.watchedUpcoming.isEmpty())
                            item {
                                EmptyMessage(
                                    "Keep a good find close",
                                    "Save a deal from the hunt. Your shortlist stays on this device.",
                                )
                            }
                        if (model.watchedUpcoming.isNotEmpty()) item { Text("Watched voucher windows", style = MaterialTheme.typography.titleMedium) }
                        items(model.watchedUpcoming, key = { it.id }) { UpcomingCard(it, model) }
                        items(model.saved, key = { it.offer.id }) { DealCard(it, model, true) }
                    }
            }
        }
    }
    if (settings)
        AlertDialog(
            onDismissRequest = { settings = false },
            title = { Text("Connection") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                    OutlinedTextField(
                        value = address,
                        onValueChange = { address = it },
                        label = { Text("Gateway URL") },
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
                    )
                    Text(
                        "Emulator: http://10.0.2.2:3202. A physical device needs a reachable gateway. Release builds require HTTPS. No model keys belong in this app.",
                        style = MaterialTheme.typography.bodySmall,
                    )
                    Text(
                        if (model.status?.dataAvailable == true) "Platform data available"
                        else "Platform not connected"
                    )
                }
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        model.updateGateway(address)
                        settings = false
                    }
                ) {
                    Text("Save & test")
                }
            },
            dismissButton = { TextButton(onClick = { settings = false }) { Text("Cancel") } },
        )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HuntScreen(model: HuntModel) {
    var query by remember { mutableStateOf("") }
    var includeSyntheticUpcoming by remember { mutableStateOf(false) }
    var budget by remember { mutableStateOf("") }
    var demo by remember { mutableStateOf(false) }
    var showFilters by remember { mutableStateOf(false) }
    var payment by remember { mutableStateOf("") }
    var variant by remember { mutableStateOf("") }
    var membership by remember { mutableStateOf("") }
    var user by remember { mutableIntStateOf(0) }
    var rank by remember { mutableIntStateOf(0) }
    val results = model.deals
    val offers =
        when (rank) {
            1 -> results?.conditional
            2 -> results?.fewest
            else -> results?.eligible
        }.orEmpty()
    LazyColumn(
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        item {
            Text("Find your next good deal.", style = MaterialTheme.typography.headlineMedium)
            Text(
                "Exact products. Eligible vouchers. The full checkout math.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        item {
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text("Upcoming voucher windows", style = MaterialTheme.typography.titleLarge)
                    Row {
                        Checkbox(includeSyntheticUpcoming, { includeSyntheticUpcoming = it })
                        Text("Include synthetic examples", Modifier.padding(top = 12.dp), style = MaterialTheme.typography.bodyMedium)
                    }
                    OutlinedButton(onClick = { model.loadUpcoming(includeSyntheticUpcoming) }, enabled = !model.loadingUpcoming, modifier = Modifier.fillMaxWidth()) {
                        if (model.loadingUpcoming) CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                        else Text(if (model.upcoming == null) "Load supplied voucher windows" else "Refresh supplied windows")
                    }
                    Text(model.upcoming?.notice ?: "Supplied dates and terms only. No prices, availability, or countdowns are inferred.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    model.upcoming?.deals?.forEach { UpcomingCard(it, model) }
                    if (model.upcoming?.deals?.isEmpty() == true) Text("No supplied future voucher windows.", style = MaterialTheme.typography.bodySmall)
                }
            }
        }
        item {
            OutlinedTextField(
                query,
                { query = it },
                label = { Text("Product or exact model") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
            )
        }
        item {
            OutlinedTextField(
                budget,
                { budget = it.filter(Char::isDigit) },
                label = { Text("Target checkout · VND") },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
            )
        }
        item {
            Row {
                Checkbox(demo, { demo = it })
                Text(
                    "Include synthetic demo offers",
                    Modifier.padding(top = 12.dp),
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
        }
        item {
            OutlinedButton(onClick = { showFilters = true }, modifier = Modifier.fillMaxWidth()) {
                Text("Voucher eligibility & exact variant")
            }
        }
        item {
            Button(
                onClick = {
                    model.hunt(
                        HuntRequest(
                            query,
                            budget.toLongOrNull(),
                            variant.ifBlank { null },
                            demo,
                            Eligibility(
                                payment.ifBlank { null },
                                membership
                                    .takeIf { it.isNotBlank() }
                                    ?.split(',')
                                    ?.map { it.trim() },
                                if (user == 0) null else user == 1,
                            ),
                        )
                    )
                },
                enabled = query.trim().length >= 2 && !model.hunting,
                modifier = Modifier.fillMaxWidth(),
            ) {
                if (model.hunting)
                    CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                else Text("Find deals")
            }
        }
        if (results != null) {
            item {
                SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                    listOf("Eligible", "Conditional", "Fewer rules").forEachIndexed { i, title ->
                        SegmentedButton(
                            selected = rank == i,
                            onClick = { rank = i },
                            shape = SegmentedButtonDefaults.itemShape(i, 3),
                        ) {
                            Text(title)
                        }
                    }
                }
                Text(
                    results.notice,
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.padding(top = 12.dp),
                )
            }
            if (offers.isEmpty())
                item {
                    EmptyMessage(
                        "No matching offers",
                        "Try a specific product or change eligibility. Live offers need a validated feed.",
                    )
                }
            items(offers, key = { it.offer.id }) { DealCard(it, model) }
        } else
            item {
                EmptyMessage(
                    "Make a specific find",
                    "Demo data is opt-in and never represents current marketplace offers.",
                )
            }
    }
    if (showFilters)
        ModalBottomSheet(onDismissRequest = { showFilters = false }) {
            Column(
                Modifier.padding(24.dp).fillMaxWidth().verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                Text("Voucher eligibility", style = MaterialTheme.typography.titleLarge)
                OutlinedTextField(
                    payment,
                    { payment = it },
                    label = { Text("Payment method · unknown if blank") },
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    variant,
                    { variant = it },
                    label = { Text("Exact variant / warranty key") },
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    membership,
                    { membership = it },
                    label = { Text("Memberships, comma-separated") },
                    modifier = Modifier.fillMaxWidth(),
                )
                Text("New-user eligibility", style = MaterialTheme.typography.labelLarge)
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf("Unknown", "Eligible", "Not eligible").forEachIndexed { i, label ->
                        FilterChip(
                            selected = user == i,
                            onClick = { user = i },
                            label = { Text(label) },
                            modifier = Modifier.padding(end = 8.dp),
                        )
                    }
                }
                Text(
                    "Used for this search. No personal profile is created.",
                    style = MaterialTheme.typography.bodySmall,
                )
                Button(onClick = { showFilters = false }, modifier = Modifier.fillMaxWidth()) {
                    Text("Done")
                }
                Spacer(Modifier.height(20.dp))
            }
        }
}

@Composable
fun UpcomingCard(deal: UpcomingDeal, model: HuntModel) {
    val context = LocalContext.current
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
            Row {
                Column(Modifier.weight(1f)) { Text(deal.code, style = MaterialTheme.typography.titleMedium); Text(deal.platform + (deal.seller?.let { " · $it" } ?: ""), style = MaterialTheme.typography.bodySmall) }
                IconButton(onClick = { model.toggleUpcoming(deal) }) {
                    Icon(if (model.watchedUpcoming.any { it.id == deal.id }) Icons.Outlined.Bookmark else Icons.Outlined.BookmarkBorder, "Toggle device-local watchlist")
                }
            }
            Text("Starts: " + deal.startsAt, style = MaterialTheme.typography.bodySmall)
            Text("Ends: " + deal.expiresAt, style = MaterialTheme.typography.bodySmall)
            Text(if (deal.percent > 0) "Discount: ${deal.percent}% · cap ${deal.cap?.let { money(it) } ?: "No stated cap"}" else "Discount: ${money(deal.discount)}", style = MaterialTheme.typography.bodyMedium)
            Text("Minimum spend: " + money(deal.minimumSpend), style = MaterialTheme.typography.bodySmall)
            if (deal.productKeys.isNotEmpty()) Text("Applies to: " + deal.productKeys.joinToString(" · "), style = MaterialTheme.typography.bodySmall)
            if (deal.eligibility.isNotEmpty()) Text("Eligibility: " + deal.eligibility.joinToString(" · "), style = MaterialTheme.typography.bodySmall)
            deal.checkoutPaymentMethod?.let { Text("Checkout payment method: $it", style = MaterialTheme.typography.bodySmall) }
            Text("Future cashback · separate from checkout: " + money(deal.cashback), style = MaterialTheme.typography.bodySmall)
            Text("Evidence: ${deal.evidenceSource} · as of ${deal.asOf}${if (deal.synthetic) " · synthetic example" else ""}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            deal.evidenceUrl?.let { source -> if (Uri.parse(source).scheme in listOf("http", "https")) TextButton(onClick = { runCatching { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(source))) } }) { Text("Open voucher evidence") } }
        }
    }
}

@Composable
fun DealCard(deal: Deal, model: HuntModel, snapshot: Boolean = false) {
    var expanded by remember { mutableStateOf(false) }
    val context = LocalContext.current
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row {
                Surface(
                    color = MaterialTheme.colorScheme.secondaryContainer,
                    shape = MaterialTheme.shapes.small,
                ) {
                    Text(
                        if (deal.offer.sourceTier == "synthetic") "Synthetic demo"
                        else deal.offer.sourceTier,
                        Modifier.padding(8.dp),
                        style = MaterialTheme.typography.labelSmall,
                    )
                }
                Spacer(Modifier.weight(1f))
                IconButton(onClick = { model.toggle(deal) }) {
                    Icon(
                        if (model.saved.any { it.offer.id == deal.offer.id })
                            Icons.Outlined.Favorite
                        else Icons.Outlined.FavoriteBorder,
                        "Toggle saved deal",
                    )
                }
            }
            Text(deal.offer.title, style = MaterialTheme.typography.titleLarge)
            Text(
                deal.offer.seller + " · " + deal.offer.platform,
                style = MaterialTheme.typography.bodySmall,
            )
            Text(money(deal.checkout), style = MaterialTheme.typography.headlineMedium)
            Text(
                if (deal.eligible) "Eligible estimate · confirm at checkout"
                else "Conditions apply",
                style = MaterialTheme.typography.labelMedium,
            )
            if (snapshot)
                Text(
                    "Saved snapshot. Recheck current availability.",
                    style = MaterialTheme.typography.bodySmall,
                )
            TextButton(onClick = { expanded = !expanded }) {
                Text(if (expanded) "Hide price breakdown" else "How this price works")
            }
            if (expanded) {
                PriceLine("Item price", deal.offer.price)
                deal.discounts.forEach { PriceLine(it.code + " · " + it.scope, -it.amount) }
                PriceLine("Delivery after vouchers", deal.shipping)
                HorizontalDivider()
                PriceLine("Payable estimate", deal.checkout)
                PriceLine("Future cashback · separate", deal.cashback)
                Text(
                    "Variant: " + deal.offer.productKey,
                    style = MaterialTheme.typography.bodySmall,
                )
                Text(
                    "Observed: " + observedTime(deal.offer.observed),
                    style = MaterialTheme.typography.bodySmall,
                )
                deal.historyLow?.let {
                    Text(
                        "Prior item low: " +
                            money(it) +
                            " · " +
                            deal.historyDays +
                            " observed dates. Gaps may exist; before vouchers.",
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
            }
            deal.conditions.forEach {
                Text(
                    it,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            deal.offer.url?.let { url ->
                if (Uri.parse(url).scheme in listOf("https", "http"))
                    TextButton(
                        onClick = {
                            runCatching {
                                context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
                            }
                        }
                    ) {
                        Text("View listing")
                    }
            }
        }
    }
}

@Composable
fun PriceLine(label: String, amount: Long?) {
    Row(Modifier.fillMaxWidth()) {
        Text(label, Modifier.weight(1f), style = MaterialTheme.typography.bodySmall)
        Text(money(amount), style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
fun EmptyMessage(title: String, body: String) {
    Column(
        Modifier.fillMaxWidth().padding(vertical = 24.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Text(title, style = MaterialTheme.typography.titleMedium)
        Text(
            body,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
fun DiscoverScreen(model: HuntModel) {
    var query by remember { mutableStateOf("") }
    var demo by remember { mutableStateOf(false) }
    val context = LocalContext.current
    LazyColumn(
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        item {
            OutlinedTextField(
                query,
                { query = it },
                label = { Text("Product, model or brand") },
                modifier = Modifier.fillMaxWidth(),
            )
            Row {
                Checkbox(demo, { demo = it })
                Text("Include synthetic data", Modifier.padding(top = 12.dp))
            }
            Button(
                onClick = { model.discover(query, demo) },
                enabled = query.length >= 2 && !model.discovering,
            ) {
                Text("Search products")
            }
        }
        if (model.products.isEmpty())
            item {
                EmptyMessage(
                    "Find something specific",
                    "Fresh indexed listing candidates. Delivery, vouchers and exact variant matching are separate.",
                )
            }
        items(model.products, key = { it.id }) { p ->
            Card {
                Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(p.title, style = MaterialTheme.typography.titleMedium)
                    Text(money(p.price), style = MaterialTheme.typography.headlineSmall)
                    Text(
                        p.platform + " · " + p.sourceTier,
                        style = MaterialTheme.typography.bodySmall,
                    )
                    Text(
                        "Observed: " + observedTime(p.captured),
                        style = MaterialTheme.typography.bodySmall,
                    )
                    p.url?.let { url ->
                        if (Uri.parse(url).scheme in listOf("http", "https"))
                            TextButton(
                                onClick = {
                                    runCatching {
                                        context.startActivity(
                                            Intent(Intent.ACTION_VIEW, Uri.parse(url))
                                        )
                                    }
                                }
                            ) {
                                Text("View listing")
                            }
                    }
                }
            }
        }
    }
}

@Composable
fun HomeUpcomingWidget(model: HuntModel, openHunt: () -> Unit) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row {
                Text("Upcoming voucher windows", Modifier.weight(1f), style = MaterialTheme.typography.titleMedium)
                TextButton(onClick = openHunt) { Text("See all") }
            }
            val results = model.upcoming
            when {
                model.loadingUpcoming && results == null -> LinearProgressIndicator(Modifier.fillMaxWidth())
                results == null -> {
                    Text("Connect to view supplied dates and terms. No prices or countdowns are inferred.", style = MaterialTheme.typography.bodySmall)
                    OutlinedButton(onClick = { model.loadUpcoming(includeSynthetic = false) }) { Text("Load supplied windows") }
                }
                results.deals.isEmpty() -> Text("No supplied future voucher windows.", style = MaterialTheme.typography.bodySmall)
                else -> {
                    UpcomingCard(results.deals.first(), model)
                    if (results.deals.size > 1) Text("Showing one of ${results.deals.size} supplied windows; see all for the complete list.", style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }
}

@Composable
fun ChatScreen(model: HuntModel, openHunt: () -> Unit) {
    var draft by remember { mutableStateOf("") }
    var useModel by remember { mutableStateOf(false) }
    val chatListState = rememberLazyListState()
    LaunchedEffect(model.messages.size, model.chatting) {
        if (model.messages.isNotEmpty())
            chatListState.animateScrollToItem(
                model.messages.lastIndex + if (model.chatting) 1 else 0
            )
    }
    Column(Modifier.fillMaxSize()) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp)) {
            TextButton(onClick = model::newChat, enabled = !model.chatting) {
                Text("New conversation")
            }
            Spacer(Modifier.weight(1f))
            Text(
                if (model.status?.modelConfigured == true) "Model configured" else "Data mode",
                style = MaterialTheme.typography.labelSmall,
                modifier = Modifier.padding(top = 16.dp),
            )
        }
        LazyColumn(
            Modifier.weight(1f),
            state = chatListState,
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(20.dp),
        ) {
            item { HomeUpcomingWidget(model, openHunt) }
            if (model.messages.isEmpty())
                item {
                    EmptyMessage(
                        "Ask before checkout",
                        "Try “Compare GMV yesterday” or “Help me combine vouchers”.",
                    )
                }
            items(model.messages) { m ->
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(
                        if (m.role == "user") "You" else "Hunt",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.primary,
                    )
                    Text(m.content, style = MaterialTheme.typography.bodyMedium)
                    if (m.role == "assistant" && m.content.contains("Deal hunt"))
                        TextButton(onClick = openHunt) { Text("Open Deal hunt") }
                }
            }
            if (model.chatting) item { LinearProgressIndicator(Modifier.fillMaxWidth()) }
        }
        Surface(tonalElevation = 2.dp) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row {
                    Checkbox(
                        useModel,
                        { useModel = it },
                        enabled = model.status?.modelConfigured == true && !model.chatting,
                    )
                    Text(
                        if (model.status?.modelConfigured == true) "Use " + model.status?.model
                        else "Model not connected · fixed data queries",
                        Modifier.padding(top = 12.dp),
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
                OutlinedTextField(
                    draft,
                    { draft = it.take(8000) },
                    label = { Text("Your message") },
                    modifier = Modifier.fillMaxWidth(),
                    maxLines = 5,
                )
                Button(
                    onClick = {
                        if (model.chatting) model.stop()
                        else {
                            model.send(draft, useModel)
                            draft = ""
                        }
                    },
                    enabled = model.chatting || draft.isNotBlank(),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text(if (model.chatting) "Stop response" else "Send")
                }
                Text(
                    if (useModel) "Messages and gold context go to the configured provider."
                    else "No LLM. Supported analytics and indexed products only.",
                    style = MaterialTheme.typography.labelSmall,
                )
            }
        }
    }
}
