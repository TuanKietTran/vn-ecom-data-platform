package vn.shoplens

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
                        primary = Color(0xFFFFB4A8),
                        onPrimary = Color(0xFF650F04),
                        primaryContainer = Color(0xFF8F200F),
                        onPrimaryContainer = Color(0xFFFFDAD2),
                        secondary = Color(0xFFBACD95),
                        onSecondary = Color(0xFF26350D),
                        secondaryContainer = Color(0xFF3B4B21),
                        onSecondaryContainer = Color(0xFFD5E6AF),
                        tertiary = Color(0xFFE4C18D),
                        onTertiary = Color(0xFF402D0B),
                        tertiaryContainer = Color(0xFF59441B),
                        onTertiaryContainer = Color(0xFFFFDEAA),
                        background = Color(0xFF1A1210),
                        onBackground = Color(0xFFF3DED7),
                        surface = Color(0xFF1A1210),
                        onSurface = Color(0xFFF3DED7),
                        surfaceVariant = Color(0xFF53433E),
                        onSurfaceVariant = Color(0xFFD8C2BA),
                        outline = Color(0xFFA08C85),
                        surfaceContainer = Color(0xFF271E1B),
                        surfaceContainerHigh = Color(0xFF312725),
                        surfaceContainerHighest = Color(0xFF3D322F),
                        surfaceContainerLow = Color(0xFF211815),
                        surfaceContainerLowest = Color(0xFF140C0A),
                    )
                else
                    lightColorScheme(
                        primary = Color(0xFFB83320),
                        onPrimary = Color.White,
                        primaryContainer = Color(0xFFFFDAD2),
                        onPrimaryContainer = Color(0xFF3D0600),
                        secondary = Color(0xFF526132),
                        onSecondary = Color.White,
                        secondaryContainer = Color(0xFFD5E6AF),
                        onSecondaryContainer = Color(0xFF131F00),
                        tertiary = Color(0xFF735B31),
                        onTertiary = Color.White,
                        tertiaryContainer = Color(0xFFFFDEAA),
                        onTertiaryContainer = Color(0xFF291800),
                        background = Color(0xFFFFF8F3),
                        onBackground = Color(0xFF221A17),
                        surface = Color(0xFFFFF8F3),
                        onSurface = Color(0xFF221A17),
                        surfaceVariant = Color(0xFFF4DED7),
                        onSurfaceVariant = Color(0xFF53433E),
                        outline = Color(0xFF85736D),
                        surfaceContainer = Color(0xFFF3E6DF),
                        surfaceContainerHigh = Color(0xFFEDDFD6),
                        surfaceContainerHighest = Color(0xFFE7D8CF),
                        surfaceContainerLow = Color(0xFFFCF0E9),
                        surfaceContainerLowest = Color.White,
                    )
            MaterialTheme(colorScheme = colors) { ShopApp() }
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

class ShopModel(app: Application) : AndroidViewModel(app) {
    private val preferences = app.getSharedPreferences("shoplens", 0)
    var base by mutableStateOf(preferences.getString("gateway", "http://10.0.2.2:4100")!!)
        private set

    var status by mutableStateOf<Status?>(null)
        private set

    var deals by mutableStateOf<DealResults?>(null)
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
fun ShopApp(model: ShopModel = viewModel()) {
    var tab by remember { mutableIntStateOf(0) }
    var settings by remember { mutableStateOf(false) }
    var address by remember { mutableStateOf(model.base) }
    val labels = listOf("Hunt", "Discover", "Ask", "Saved")
    val icons =
        listOf(
            Icons.Outlined.LocalActivity,
            Icons.Outlined.Search,
            Icons.Outlined.ChatBubbleOutline,
            Icons.Outlined.FavoriteBorder,
        )
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(if (tab == 2) "Ask ShopLens" else labels[tab]) },
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
                        icon = { Icon(icons[i], null) },
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
                0 -> HuntScreen(model)
                1 -> DiscoverScreen(model)
                2 -> ChatScreen(model) { tab = 0 }
                else ->
                    LazyColumn(
                        contentPadding = PaddingValues(16.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        item {
                            Text(
                                "Saved snapshots. Recheck current price and voucher availability.",
                                style = MaterialTheme.typography.bodySmall,
                            )
                        }
                        if (model.saved.isEmpty())
                            item {
                                EmptyMessage(
                                    "Keep a good find close",
                                    "Save a deal from the hunt. Your shortlist stays on this device.",
                                )
                            }
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
                        "Emulator: http://10.0.2.2:4100. A physical device needs a reachable gateway. Release builds require HTTPS. No model keys belong in this app.",
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
fun HuntScreen(model: ShopModel) {
    var query by remember { mutableStateOf("") }
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
                Modifier.padding(24.dp).fillMaxWidth(),
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
                Row {
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
fun DealCard(deal: Deal, model: ShopModel, snapshot: Boolean = false) {
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
fun DiscoverScreen(model: ShopModel) {
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
fun ChatScreen(model: ShopModel, openHunt: () -> Unit) {
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
                        if (m.role == "user") "You" else "ShopLens",
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
